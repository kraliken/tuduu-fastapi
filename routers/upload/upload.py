from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import StreamingResponse
import base64
from sqlmodel import select
from sqlalchemy.orm import selectinload
from azure.communication.email import EmailClient
import os
import io
from database.connection import SessionDep
from database.models import (
    User,
    PhoneBook,
    TeszorMapping,
    TeszorCode,
    LedgerAccount,
    VatSetting,
)
from typing import Annotated
from routers.auth.oauth2 import get_current_user
import pandas as pd
from services.invoice_processor import InvoiceProcessor
import re


router = APIRouter(prefix="/upload", tags=["upload"])

email_client = EmailClient.from_connection_string(
    os.getenv("AZURE_EMAIL_CONNECTION_STRING")
)


@router.post("/vodafone")
async def upload(
    # current_user: Annotated[User, Depends(get_current_user)],
    session: SessionDep,
    file: UploadFile = File(...),
    # email: str = Form(...),
):

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="A feltöltött fájl nem PDF.")

    file_bytes = await file.read()
    file_base64 = base64.b64encode(file_bytes).decode("utf-8")

    try:
        processor = InvoiceProcessor(file_bytes)
        result = processor.process()

        if not result["invoice_summary"] and not result["service_charges"]:
            raise HTTPException(
                status_code=400, detail="No relevant invoice data found in the PDF."
            )

        # 🔹 Telefonszám → Tulajdonos betöltés (dict)
        phone_user_map = {
            row.phone_number: row.owner for row in session.exec(select(PhoneBook)).all()
        }

        teszor_mappings = session.exec(
            select(TeszorMapping)
            .join(TeszorCode)
            .join(LedgerAccount)
            .join(VatSetting)
            .options(
                selectinload(TeszorMapping.teszor_code),
                selectinload(TeszorMapping.ledger_account),
                selectinload(TeszorMapping.vat_setting),
            )
        ).all()

        teszor_category_map = {
            mapping.teszor_code.teszor_code: mapping.ledger_account.title
            for mapping in teszor_mappings
            if mapping.teszor_code and mapping.ledger_account
        }

        mapping_lookup = {
            (m.teszor_code.teszor_code, m.vat_setting.rate): {
                "Title": m.ledger_account.title,
                "VatCode": m.vat_setting.code,
                "LedgerAccount": m.ledger_account.account_number,
            }
            for m in teszor_mappings
            if m.teszor_code and m.vat_setting and m.ledger_account
        }

        def extract_mapping_info(row):
            key = (row["TESZOR"], row["VATRate"])

            return pd.Series(
                mapping_lookup.get(
                    key,
                    {
                        "Title": "Ismeretlen",
                        "VatCode": "Ismeretlen",
                        "LedgerAccount": "Ismeretlen",
                    },
                )
            )

        def _clean_float(value):
            try:
                cleaned = value.replace(".", "").replace(",", ".").strip()
                return float(cleaned) if re.match(r"^-?\d+(\.\d+)?$", cleaned) else None
            except Exception:
                return None

        excel_buffer = io.BytesIO()

        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            if result["invoice_summary"]:
                # df_summary = pd.DataFrame(result["invoice_summary"])

                df_summary = pd.DataFrame(
                    result["invoice_summary"],
                    columns=[
                        "Megnevezés",
                        "Mennyiség",
                        "Mennyiségi egység",
                        "Egységár (Ft)",
                        "TESZOR szám",
                        "ÁFA kulcs",
                        "Nettó összeg (Ft)",
                        "ÁFA összeg (Ft)",
                        "Bruttó összeg (Ft)",
                    ],
                )

                for col in [
                    "Egységár (Ft)",
                    "Nettó összeg (Ft)",
                    "ÁFA összeg (Ft)",
                    "Bruttó összeg (Ft)",
                ]:
                    df_summary[col] = (
                        df_summary[col]
                        .astype(str)
                        .str.replace(".", "", regex=False)
                        .str.replace(",", ".", regex=False)
                        .astype(float)
                    )

                df_summary.to_excel(writer, sheet_name="InvoiceSummary", index=False)
            # ---------------------------------------------------------------------------------------
            if result["service_charges"]:
                df_charges = pd.DataFrame(
                    result["service_charges"],
                    columns=[
                        "PhoneNumber",
                        "Description",
                        "TESZOR",
                        "TotalAmount",
                        "VATAmount",
                        "VATRate",
                        "NetAmount",
                    ],
                )
                df_charges["Employee"] = (
                    df_charges["PhoneNumber"].map(phone_user_map).fillna("N/A")
                )
                df_charges["LedgerTitle"] = (
                    df_charges["TESZOR"].map(teszor_category_map).fillna("N/A")
                )

                title_df = df_charges.apply(extract_mapping_info, axis=1)
                df = pd.concat([df_charges, title_df], axis=1)

                for col in ["NetAmount", "VATAmount", "TotalAmount"]:
                    df[col] = df_charges[col].apply(_clean_float)
                # ---------------------------------------------------------------------------------------
                df.to_excel(writer, sheet_name="ServiceCharges", index=False)

            if not df.empty:
                pivot_df = pd.pivot_table(
                    df,
                    index=[
                        "PhoneNumber",
                        "Employee",
                        "VATRate",
                        "Title",
                        "VatCode",
                        "LedgerAccount",
                    ],
                    values=["NetAmount", "VATAmount"],
                    aggfunc="sum",
                    fill_value=0,
                ).reset_index()

                pivot_df.to_excel(writer, sheet_name="Kimutatás", index=False)

        excel_buffer.seek(0)

        return StreamingResponse(
            excel_buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=invoice_data.xlsx"},
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")

    message = {
        "content": {
            "subject": "Riport készítés teszt",
            "plainText": "Csatolva a számla és a kinyert adatok.",
        },
        "recipients": {
            "to": [
                {
                    "address": email,
                    "displayName": email,
                }
            ],
            "cc": [
                {
                    "address": "kraaliknorbert@gmail.com",  # Email address. Required.
                    "displayName": "Norbert Králik",  # Optional. Email display name.
                }
            ],
        },
        "senderAddress": "donotreply@75ddf508-e558-4566-8a15-7ef476187504.azurecomm.net",
        "attachments": [
            {
                "name": file.filename,
                "contentType": "application/pdf",
                "contentInBase64": file_base64,
            }
        ],
    }

    return {
        "success": True,
        "message": "Invoice successfully uploaded!",
        "data": {},
    }
    # try:
    #     poller = email_client.begin_send(message)
    #     result = poller.result()

    #     if result["status"] == "Succeeded":
    #         # return {"message": "Email elküldve", "operation_id": result["id"]}
    #         return {
    #             "success": True,
    #             "message": "Invoice successfully uploaded!",
    #             "operation_id": result["id"],
    #             "data": {"filename": file.filename, "email": email},
    #         }
    #     else:
    #         raise HTTPException(status_code=500, detail=str(result["error"]))

    # except Exception as ex:
    #     raise HTTPException(status_code=500, detail=f"Email küldési hiba: {ex}")
