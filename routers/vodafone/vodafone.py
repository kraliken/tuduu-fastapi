from fastapi import APIRouter, Depends, status, HTTPException, Response
from typing import Annotated
from database.connection import SessionDep
from database.models import PhoneBook, LedgerAccount, VatSetting, User, TeszorCode
from routers.auth.oauth2 import get_current_user
from sqlmodel import select, func, case


router = APIRouter(prefix="/vodafone", tags=["vodafone"])


@router.get("/extraction-support")
def get_extraction_support_data(
    # current_user: Annotated[User, Depends(get_current_user)],
    session: SessionDep,
):
    phonebook = session.exec(select(PhoneBook)).all()
    ledger_accounts = session.exec(select(LedgerAccount)).all()
    vat_settings = session.exec(select(VatSetting)).all()
    teszor_codes = session.exec(select(TeszorCode)).all()

    return {
        "phonebook": phonebook,
        "ledger_accounts": ledger_accounts,
        "vat_settings": vat_settings,
        "teszor_codes": teszor_codes,
    }
