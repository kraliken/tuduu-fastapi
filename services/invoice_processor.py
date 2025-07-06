import pdfplumber
import io
import re


class InvoiceProcessor:
    def __init__(self, pdf_bytes: bytes):
        self.pdf_bytes = pdf_bytes
        self.invoice_summary_rows = []
        self.service_charge_rows = []

    def process(self):
        with pdfplumber.open(io.BytesIO(self.pdf_bytes)) as pdf:

            is_service_section = False
            service_lines_accumulator = []

            for page in pdf.pages:
                text = page.extract_text() or ""
                if not text:
                    continue
                lines = text.split("\n")
                header = lines[0].strip().upper()

                if header in ["KISZÁMLÁZOTT DÍJAK", "ÜGYFÉLSZINTŰ DÍJAK"]:
                    is_service_section = True
                    service_lines_accumulator.extend(lines)

                elif is_service_section:
                    service_lines_accumulator.extend(lines)

                if is_service_section and any(
                    "Kiszámlázott díjak összesen" in line for line in lines
                ):
                    self._process_service_charges(service_lines_accumulator)
                    is_service_section = False
                    service_lines_accumulator = []

                if header == "SZÁMLA":
                    self._process_invoice_page(text)

        return {
            "invoice_summary": self.invoice_summary_rows,
            "service_charges": self.service_charge_rows,
        }

    def _process_invoice_page(self, text: str):
        start = text.find("Számlaösszesítő")
        end = text.find("Egyenlegközlő információ")
        if start == -1 or end == -1:
            return
        for line in text[start:end].split("\n"):
            if any(
                k in line
                for k in ["összeg", "Megnevezés", "Összesen", "Számlaösszesítő"]
            ):
                continue

            teszor_match = re.search(r"\b\d{2}\.\d{2}\.\d{1,2}\b", line)
            if teszor_match:
                parts = line.rsplit(" ", 8)
                if len(parts) == 9:
                    self.invoice_summary_rows.append(parts)
            else:
                parts = line.rsplit(" ", 7)
                if len(parts) == 8:
                    parts.insert(4, "")  # empty TESZOR field
                    self.invoice_summary_rows.append(parts)

    def _process_service_charges(self, lines):
        phone_number = "N/A"
        for line in lines:
            if "Tarifacsomag:" in line:
                break
            match = re.search(r"Telefonszám:\s*(36\d{9})", line)
            if match:
                phone_number = match.group(1)
                break

        try:
            start_index = next(
                i
                for i, line in enumerate(lines)
                if line.strip().startswith("Megnevezés")
            )
            end_index = next(
                i
                for i, line in enumerate(lines)
                if line.strip().startswith("Kiszámlázott díjak összesen")
            )
        except StopIteration:
            return

        for line in lines[start_index + 1 : end_index]:
            teszor_match = re.search(r"\b\d{2}\.\d{2}\.\d{1,2}\b", line)
            if not teszor_match:
                continue

            teszor = teszor_match.group()
            parts = line.rsplit(" ", 4)
            if len(parts) < 5:
                continue

            total_amount, vat_amount, vat_rate, net_amount = parts[-4:]
            before_values = parts[0]
            description = (
                before_values.split(teszor)[0].strip()
                if teszor in before_values
                else before_values.strip()
            )

            self.service_charge_rows.append(
                [
                    phone_number,
                    description,
                    teszor,
                    net_amount,
                    vat_rate,
                    vat_amount,
                    total_amount,
                ]
            )
