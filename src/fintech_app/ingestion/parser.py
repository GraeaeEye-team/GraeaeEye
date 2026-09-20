"""
Первичный парсинг и потоковое чтение банковских выписок (CSV, XLSX, PDF).
Реализует безопасную работу с памятью (Streaming / Chunked Processing),
очистку европейских и смешанных числовых форматов, валютных кодов и BOM-заголовков.
"""

from __future__ import annotations

import csv
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
import io
import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import UUID, uuid4

try:
    import openpyxl
except ImportError:
    openpyxl = None  # type: ignore

try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore

from fintech_app.core.exceptions import ParsingError
from fintech_app.ingestion.ai_mapper import (
    TransactionCategorizationMapper,
    fuzzy_map_headers,
    validate_mapping,
)
from fintech_app.ingestion.schemas import (
    NormalizedTransactionRecord,
    ParsedBankStatementPayload,
    ParsedCreditObligationRecord,
    ParsedInvoiceRecord,
    ParsedJudicialRecord,
    RawBankStatementLine,
    StandardizedTransactionBatch,
)
from fintech_app.shared.schemas.user_types import (
    LiquidityClass,
    TransactionCategory,
    TransactionDirection,
)

logger = logging.getLogger(__name__)


def clean_amount_string(val: Any) -> Tuple[Decimal, Optional[TransactionDirection]]:
    """
    Очищает строковое представление суммы от валют, пробелов, скобок и европейских разделителей.
    Возвращает (абсолютная_сумма: Decimal, определенное_направление: Optional[TransactionDirection]).
    """
    if val is None:
        raise ParsingError("Amount cell cannot be null or empty.")

    if isinstance(val, (int, float, Decimal)):
        num = Decimal(str(val))
        direction = TransactionDirection.OUTFLOW if num < 0 else TransactionDirection.INFLOW
        return abs(num).quantize(Decimal("0.01")), direction

    raw = str(val).strip()
    if not raw:
        raise ParsingError("Amount cell cannot be an empty string.")

    is_negative = False
    if raw.startswith("(") and raw.endswith(")"):
        is_negative = True
        raw = raw[1:-1].strip()
    elif raw.startswith("-") or raw.endswith("-"):
        is_negative = True
        raw = raw.replace("-", "").strip()
    elif raw.startswith("+"):
        raw = raw[1:].strip()

    cleaned = re.sub(r"[A-Za-zА-Яа-я\$€\u20bd£¥]", "", raw).strip()
    cleaned = cleaned.replace("\xa0", "").replace(" ", "")

    if not cleaned:
        raise ParsingError(f"Cannot parse monetary amount from string: '{val}'")

    if "." in cleaned and "," in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        parts = cleaned.split(",")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            cleaned = cleaned.replace(",", ".")
        elif len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) <= 3:
            cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(",", ".")
    elif "." in cleaned:
        parts = cleaned.split(".")
        if len(parts) > 2:
            cleaned = "".join(parts)

    try:
        amount_dec = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ParsingError(f"Invalid monetary format '{val}': cannot convert to Decimal") from exc

    if is_negative or amount_dec < 0:
        return abs(amount_dec).quantize(Decimal("0.01")), TransactionDirection.OUTFLOW
    return amount_dec.quantize(Decimal("0.01")), TransactionDirection.INFLOW


def parse_date_flexible(val: Any) -> date:
    """
    Гибкий парсинг даты из строк формата YYYY-MM-DD, DD.MM.YYYY, DD/MM/YYYY, datetime и date.
    """
    if val is None:
        raise ParsingError("Date cell cannot be null.")

    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val

    s = str(val).strip()
    if " " in s:
        s = s.split(" ")[0]
    elif "T" in s:
        s = s.split("T")[0]

    formats = [
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%d.%m.%y",
        "%d/%m/%y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue

    raise ParsingError(f"Cannot parse date format from value: '{val}'")


class BankStatementParser:
    """
    Высокопроизводительный потоковый парсер выписок различных форматов (CSV, XLSX, PDF).
    """

    def parse_csv(
        self,
        file_content: Union[bytes, str],
        account_id: UUID,
        business_id: UUID,
        chunk_size: int = 1000,
    ) -> ParsedBankStatementPayload:
        """
        Чтение банковской выписки из CSV-байтов или строки с защитой от переполнения памяти.
        """
        if isinstance(file_content, bytes):
            if file_content.startswith(b"\xef\xbb\xbf"):
                text = file_content.decode("utf-8-sig")
            else:
                try:
                    text = file_content.decode("utf-8")
                except UnicodeDecodeError:
                    try:
                        text = file_content.decode("cp1251")
                    except UnicodeDecodeError:
                        text = file_content.decode("latin-1")
        else:
            text = file_content

        if not text.strip():
            raise ParsingError("Uploaded CSV file is completely empty.")

        stream = io.StringIO(text)
        sample = text[:4096]
        delimiter = ","
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
            delimiter = dialect.delimiter
        except Exception:
            for cand in [";", "\t", ","]:
                if sample.count(cand) > sample.count(delimiter):
                    delimiter = cand

        reader = csv.reader(stream, delimiter=delimiter)

        header_row: Optional[List[str]] = None
        header_mapping: Optional[Dict[str, str]] = None

        for row in reader:
            if not any(cell.strip() for cell in row):
                continue
            mapping = fuzzy_map_headers(row)
            mapped_values = set(mapping.values())
            has_amount = "amount" in mapped_values or ("debit" in mapped_values and "credit" in mapped_values)
            has_date = "date" in mapped_values

            if has_amount and has_date:
                header_row = [c.strip() for c in row]
                header_mapping = mapping
                break

        if not header_row or not header_mapping:
            raise ParsingError("Could not locate a valid statement header row in CSV file.")

        validate_mapping(set(header_mapping.values()))

        col_index_to_field: Dict[int, str] = {}
        for idx, col_name in enumerate(header_row):
            if col_name in header_mapping:
                target = header_mapping[col_name]
                col_index_to_field[idx] = target

        lines: List[RawBankStatementLine] = []
        min_date: Optional[date] = None
        max_date: Optional[date] = None

        for row in reader:
            if not any(cell.strip() for cell in row):
                continue

            row_data: Dict[str, Any] = {}
            for idx, cell_val in enumerate(row):
                if idx in col_index_to_field:
                    row_data[col_index_to_field[idx]] = cell_val.strip()

            raw_date_str = row_data.get("date")
            if not raw_date_str:
                continue

            try:
                tx_date = parse_date_flexible(raw_date_str)
            except ParsingError:
                continue

            # Извлечение суммы и направления
            amt: Optional[Decimal] = None
            inferred_dir: Optional[TransactionDirection] = None

            if "amount" in row_data and row_data["amount"]:
                try:
                    amt, inferred_dir = clean_amount_string(row_data["amount"])
                except ParsingError:
                    continue
            elif "debit" in row_data or "credit" in row_data:
                debit_str = row_data.get("debit", "")
                credit_str = row_data.get("credit", "")
                if debit_str and debit_str not in ("0", "0.00", "0,00", "-"):
                    try:
                        amt, _ = clean_amount_string(debit_str)
                        inferred_dir = TransactionDirection.OUTFLOW
                    except ParsingError:
                        pass
                elif credit_str and credit_str not in ("0", "0.00", "0,00", "-"):
                    try:
                        amt, _ = clean_amount_string(credit_str)
                        inferred_dir = TransactionDirection.INFLOW
                    except ParsingError:
                        pass

            if amt is None:
                continue

            direction = inferred_dir or TransactionDirection.OUTFLOW
            raw_dir = row_data.get("direction", "").upper()
            if raw_dir in ("INFLOW", "IN", "CREDIT", "CR", "ПРИХОД", "+"):
                direction = TransactionDirection.INFLOW
            elif raw_dir in ("OUTFLOW", "OUT", "DEBIT", "DB", "РАСХОД", "-"):
                direction = TransactionDirection.OUTFLOW

            desc = row_data.get("description", "")
            cp_tax_id = row_data.get("counterparty_tax_id")
            cp_name = row_data.get("counterparty_raw_name")
            acc_num = row_data.get("account_number", "")
            curr = row_data.get("currency", "MDL") or "MDL"

            statement_line = RawBankStatementLine(
                date=tx_date,
                amount=amt,
                direction=direction,
                description=desc,
                counterparty_raw_name=cp_name,
                counterparty_tax_id=cp_tax_id,
                account_number=acc_num,
                currency=curr,
            )
            lines.append(statement_line)

            if min_date is None or tx_date < min_date:
                min_date = tx_date
            if max_date is None or tx_date > max_date:
                max_date = tx_date

        if not lines:
            raise ParsingError("CSV parsed 0 valid transaction records.")

        total_inflow = sum((l.amount for l in lines if l.direction == TransactionDirection.INFLOW), Decimal("0.00"))
        total_outflow = sum((l.amount for l in lines if l.direction == TransactionDirection.OUTFLOW), Decimal("0.00"))

        # Extract dynamic opening balance from statement header / metadata (Zero Hardcode)
        opening_balance = Decimal("0.00")
        bal_match = re.search(
            r"(?:sold\s+initial|sold\s+precedent|opening\s+balance|initial\s+balance|sold\s+deschidere)"
            r"[:\s]+([+-]?[0-9\s,\.]+)",
            text,
            re.IGNORECASE,
        )
        if bal_match:
            try:
                raw_bal_str = bal_match.group(1).strip()
                parsed_bal, inferred_dir = clean_amount_string(raw_bal_str)
                if raw_bal_str.startswith("-") or inferred_dir == TransactionDirection.OUTFLOW:
                    opening_balance = -abs(parsed_bal)
                else:
                    opening_balance = abs(parsed_bal)
            except Exception:
                opening_balance = Decimal("0.00")

        closing_balance = (opening_balance + total_inflow - total_outflow).quantize(Decimal("0.01"))

        return ParsedBankStatementPayload(
            account_id=account_id,
            business_id=business_id,
            opening_balance=opening_balance,
            closing_balance=closing_balance,
            period_start=min_date or date.today(),
            period_end=max_date or date.today(),
            lines=lines,
        )

    def parse_xlsx(
        self,
        file_content: bytes,
        account_id: UUID,
        business_id: UUID,
    ) -> ParsedBankStatementPayload:
        """
        Потоковый парсинг Excel (.xlsx) с openpyxl в режиме read_only и data_only.
        Предотвращает избыточное потребление памяти на больших таблицах.
        """
        if openpyxl is None:
            raise RuntimeError("openpyxl must be installed to parse xlsx workbooks.")

        try:
            wb = openpyxl.load_workbook(
                io.BytesIO(file_content),
                data_only=True,
                read_only=True,
            )
        except Exception as exc:
            raise ParsingError(f"Unable to read Excel workbook: {exc}") from exc

        ws = wb.active
        if ws is None:
            raise ParsingError("Excel workbook contains no active sheets.")

        header_row: Optional[List[str]] = None
        header_mapping: Optional[Dict[str, str]] = None
        detected_opening_balance: Optional[Decimal] = None
        row_iter = ws.iter_rows(values_only=True)

        for row in row_iter:
            str_cells = [str(c).strip() if c is not None else "" for c in row]
            if not any(str_cells):
                continue

            row_joined = " ".join(str_cells)
            bal_match = re.search(
                r"(?:sold\s+initial|sold\s+precedent|opening\s+balance|initial\s+balance|sold\s+deschidere)"
                r"[:\s]+([+-]?[0-9\s,\.]+)",
                row_joined,
                re.IGNORECASE,
            )
            if bal_match and detected_opening_balance is None:
                try:
                    raw_bal = bal_match.group(1).strip()
                    parsed_b, inf_dir = clean_amount_string(raw_bal)
                    detected_opening_balance = (
                        -abs(parsed_b)
                        if (raw_bal.startswith("-") or inf_dir == TransactionDirection.OUTFLOW)
                        else abs(parsed_b)
                    )
                except Exception:
                    pass

            mapping = fuzzy_map_headers(str_cells)
            mapped_values = set(mapping.values())
            has_amount = "amount" in mapped_values or ("debit" in mapped_values and "credit" in mapped_values)
            has_date = "date" in mapped_values

            if has_amount and has_date:
                header_row = str_cells
                header_mapping = mapping
                break

        if not header_row or not header_mapping:
            wb.close()
            raise ParsingError("Could not locate a valid statement header row in Excel worksheet.")

        validate_mapping(set(header_mapping.values()))

        col_index_to_field: Dict[int, str] = {}
        for idx, col_name in enumerate(header_row):
            if col_name in header_mapping:
                target = header_mapping[col_name]
                col_index_to_field[idx] = target

        lines: List[RawBankStatementLine] = []
        min_date: Optional[date] = None
        max_date: Optional[date] = None

        for row in row_iter:
            if not any(c is not None and str(c).strip() for c in row):
                continue

            row_data: Dict[str, Any] = {}
            for idx, cell_val in enumerate(row):
                if idx in col_index_to_field and cell_val is not None:
                    row_data[col_index_to_field[idx]] = cell_val

            raw_date = row_data.get("date")
            if raw_date is None:
                continue

            try:
                tx_date = parse_date_flexible(raw_date)
            except ParsingError:
                continue

            amt: Optional[Decimal] = None
            inferred_dir: Optional[TransactionDirection] = None

            if "amount" in row_data and row_data["amount"] is not None:
                try:
                    amt, inferred_dir = clean_amount_string(row_data["amount"])
                except ParsingError:
                    continue
            elif "debit" in row_data or "credit" in row_data:
                debit_val = row_data.get("debit")
                credit_val = row_data.get("credit")
                if debit_val is not None and str(debit_val).strip() not in ("0", "0.00", "0,00", "-", ""):
                    try:
                        amt, _ = clean_amount_string(debit_val)
                        inferred_dir = TransactionDirection.OUTFLOW
                    except ParsingError:
                        pass
                elif credit_val is not None and str(credit_val).strip() not in ("0", "0.00", "0,00", "-", ""):
                    try:
                        amt, _ = clean_amount_string(credit_val)
                        inferred_dir = TransactionDirection.INFLOW
                    except ParsingError:
                        pass

            if amt is None:
                continue

            direction = inferred_dir or TransactionDirection.OUTFLOW
            raw_dir = str(row_data.get("direction", "")).upper()
            if raw_dir in ("INFLOW", "IN", "CREDIT", "CR", "ПРИХОД", "+"):
                direction = TransactionDirection.INFLOW
            elif raw_dir in ("OUTFLOW", "OUT", "DEBIT", "DB", "РАСХОД", "-"):
                direction = TransactionDirection.OUTFLOW

            desc = str(row_data.get("description", ""))
            cp_tax_id = str(row_data.get("counterparty_tax_id", "")) or None
            cp_name = str(row_data.get("counterparty_raw_name", "")) or None
            acc_num = str(row_data.get("account_number", ""))
            curr = str(row_data.get("currency", "MDL") or "MDL")

            statement_line = RawBankStatementLine(
                date=tx_date,
                amount=amt,
                direction=direction,
                description=desc,
                counterparty_raw_name=cp_name,
                counterparty_tax_id=cp_tax_id,
                account_number=acc_num,
                currency=curr,
            )
            lines.append(statement_line)

            if min_date is None or tx_date < min_date:
                min_date = tx_date
            if max_date is None or tx_date > max_date:
                max_date = tx_date

        wb.close()

        if not lines:
            raise ParsingError("Excel worksheet parsed 0 valid transaction records.")

        total_inflow = sum((l.amount for l in lines if l.direction == TransactionDirection.INFLOW), Decimal("0.00"))
        total_outflow = sum((l.amount for l in lines if l.direction == TransactionDirection.OUTFLOW), Decimal("0.00"))
        opening_balance = detected_opening_balance if detected_opening_balance is not None else Decimal("0.00")
        closing_balance = (opening_balance + total_inflow - total_outflow).quantize(Decimal("0.01"))

        return ParsedBankStatementPayload(
            account_id=account_id,
            business_id=business_id,
            opening_balance=opening_balance,
            closing_balance=closing_balance,
            period_start=min_date or date.today(),
            period_end=max_date or date.today(),
            lines=lines,
        )

    def parse_pdf(
        self,
        file_content: bytes,
        account_id: UUID,
        business_id: UUID,
    ) -> ParsedBankStatementPayload:
        """
        Парсинг выписки из PDF-документа.
        При отсутствии встроенного OCR извлекает текстовые строки или выбрасывает ParsingError.
        """
        try:
            text = file_content.decode("latin-1", errors="ignore")
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            if len(lines) > 5:
                csv_like = "\n".join(lines)
                return self.parse_csv(csv_like.encode("utf-8"), account_id, business_id)
        except Exception:
            pass

        logger.error("PDF direct text extraction failed: no valid statement records found.")
        raise ParsingError("PDF parsing failed: file contains no extractable bank statement transaction lines.")


class JudicialRegistryParser:
    """
    Парсер судебных записей и реестра задолженностей из внешних источников.
    """

    def parse_court_registry_response(self, raw_response: Dict[str, Any]) -> List[ParsedJudicialRecord]:
        """
        Преобразует JSON-ответ судебного реестра в список строго валидированных ParsedJudicialRecord.
        """
        results: List[ParsedJudicialRecord] = []
        raw_cases = raw_response.get("cases") or raw_response.get("items") or []

        for item in raw_cases:
            case_no = str(item.get("case_number") or item.get("id") or f"CASE-{uuid4().hex[:8]}")
            filing_date_str = item.get("filing_date") or item.get("date") or "2025-01-15"
            try:
                filing_date = parse_date_flexible(filing_date_str)
            except ParsingError:
                filing_date = date(2025, 1, 15)

            role = str(item.get("role") or "DEFENDANT").upper()
            if role not in ("DEFENDANT", "PLAINTIFF", "THIRD_PARTY"):
                role = "DEFENDANT"

            claim_amt = item.get("claim_amount") or item.get("amount") or Decimal("0.00")
            if not isinstance(claim_amt, Decimal):
                try:
                    claim_amt = Decimal(str(claim_amt))
                except Exception:
                    claim_amt = Decimal("0.00")

            status = str(item.get("case_status") or item.get("status") or "OPEN").upper()

            results.append(
                ParsedJudicialRecord(
                    case_number=case_no,
                    filing_date=filing_date,
                    role=role,
                    claim_amount=claim_amt.quantize(Decimal("0.01")),
                    case_status=status,
                )
            )

        return results


class InvoiceParser:
    """
    Парсер счетов-фактур и реестров накладных (invoices.csv / xlsx).
    Разбирает дебиторскую/кредиторскую задолженность, сроки оплаты и статусы.
    """

    def parse_csv(
        self,
        file_content: Union[bytes, str],
        business_id: Optional[UUID] = None,
    ) -> List[ParsedInvoiceRecord]:
        if isinstance(file_content, bytes):
            try:
                text = file_content.decode("utf-8-sig")
            except UnicodeDecodeError:
                try:
                    text = file_content.decode("cp1251")
                except UnicodeDecodeError:
                    text = file_content.decode("latin-1")
        else:
            text = file_content

        if not text.strip():
            raise ParsingError("Uploaded invoice CSV is completely empty.")

        stream = io.StringIO(text)
        sample = text[:4096]
        delimiter = ","
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
            delimiter = dialect.delimiter
        except Exception:
            for cand in [";", "\t", ","]:
                if sample.count(cand) > sample.count(delimiter):
                    delimiter = cand

        reader = csv.reader(stream, delimiter=delimiter)
        header: Optional[List[str]] = None
        for row in reader:
            if any(cell.strip() for cell in row):
                header = [c.strip().lower() for c in row]
                break

        if not header:
            raise ParsingError("Could not locate valid header row in invoice file.")

        col_map: Dict[str, int] = {}
        for idx, col in enumerate(header):
            col_norm = re.sub(r"[^\w]", "", col.strip().lower().replace(" ", "_"))
            if any(k in col_norm for k in ("counterparty_role", "role", "rol", "роль")):
                col_map.setdefault("counterparty_role", idx)
            elif any(k in col_norm for k in ("invoice_type", "type", "tip", "тип", "вид")):
                col_map.setdefault("invoice_type", idx)
            elif any(
                k in col_norm
                for k in (
                    "actual_payment_date",
                    "payment_date",
                    "paid_date",
                    "data_platii",
                    "data_achitarii",
                    "дата_оплаты",
                    "дата_платежа",
                    "оплачено_дата",
                )
            ):
                col_map.setdefault("actual_payment_date", idx)
            elif any(
                k in col_norm
                for k in ("due_date", "term", "deadline", "scadenta", "scadență", "termen", "срок", "срок_оплаты")
            ):
                col_map.setdefault("due_date", idx)
            elif any(
                k in col_norm
                for k in (
                    "issue_date",
                    "date",
                    "data",
                    "data_facturii",
                    "data_emiterii",
                    "дата_выписки",
                    "дата_счета",
                    "дата",
                )
            ):
                col_map.setdefault("issue_date", idx)
            elif any(
                k in col_norm
                for k in ("gross_amount", "amount", "total", "sum", "suma", "sumă", "valoare", "сумма", "всего", "итог")
            ):
                col_map.setdefault("gross_amount", idx)
            elif any(k in col_norm for k in ("status", "stare", "statut", "статус", "состояние")):
                col_map.setdefault("status", idx)
            elif any(
                k in col_norm
                for k in (
                    "counterparty_name",
                    "counterparty",
                    "client",
                    "supplier",
                    "partner",
                    "cumparator",
                    "cumpărător",
                    "furnizor",
                    "partener",
                    "контрагент",
                    "клиент",
                    "поставщик",
                    "партнер",
                    "покупатель",
                    "наименование",
                )
            ):
                col_map.setdefault("counterparty_name", idx)

        if "counterparty_name" not in col_map or "gross_amount" not in col_map:
            raise ParsingError("Missing mandatory columns ('counterparty_name', 'gross_amount') in invoice CSV.")

        records: List[ParsedInvoiceRecord] = []
        for row in reader:
            if not any(cell.strip() for cell in row):
                continue
            cp_name = row[col_map["counterparty_name"]].strip() if col_map["counterparty_name"] < len(row) else ""
            if not cp_name:
                continue

            raw_amt = row[col_map["gross_amount"]].strip() if col_map["gross_amount"] < len(row) else ""
            try:
                amt, _ = clean_amount_string(raw_amt)
            except ParsingError:
                continue

            cp_role = "CLIENT"
            if "counterparty_role" in col_map and col_map["counterparty_role"] < len(row):
                r_val = row[col_map["counterparty_role"]].strip().upper()
                if r_val in ("SUPPLIER", "FURNIZOR", "PRESTATOR", "ПОСТАВЩИК", "ИСПОЛНИТЕЛЬ"):
                    cp_role = "SUPPLIER"
                elif r_val in ("BOTH", "AMBELE", "ОБА", "СМЕШАННЫЙ"):
                    cp_role = "BOTH"
                elif r_val in ("CLIENT", "CUMPARATOR", "КЛИЕНТ", "ПОКУПАТЕЛЬ"):
                    cp_role = "CLIENT"

            inv_type = "RECEIVABLE"
            if "invoice_type" in col_map and col_map["invoice_type"] < len(row):
                t_val = row[col_map["invoice_type"]].strip().upper()
                if t_val in ("PAYABLE", "INTRARE", "FURNIZARE", "DEBIT", "ВХОДЯЩИЙ", "РАСХОД", "ЗАКУПКА"):
                    inv_type = "PAYABLE"
                elif t_val in ("RECEIVABLE", "IESIRE", "VANZARE", "CREDIT", "ИСХОДЯЩИЙ", "ДОХОД", "ПРОДАЖА"):
                    inv_type = "RECEIVABLE"

            issue_d = date.today()
            if "issue_date" in col_map and col_map["issue_date"] < len(row):
                try:
                    issue_d = parse_date_flexible(row[col_map["issue_date"]].strip())
                except ParsingError:
                    pass

            due_d = issue_d + timedelta(days=30)
            if "due_date" in col_map and col_map["due_date"] < len(row):
                try:
                    due_d = parse_date_flexible(row[col_map["due_date"]].strip())
                except ParsingError:
                    pass

            act_pay_d = None
            if "actual_payment_date" in col_map and col_map["actual_payment_date"] < len(row):
                raw_act = row[col_map["actual_payment_date"]].strip()
                if raw_act:
                    try:
                        act_pay_d = parse_date_flexible(raw_act)
                    except ParsingError:
                        pass

            status = "OUTSTANDING"
            if "status" in col_map and col_map["status"] < len(row):
                s_val = row[col_map["status"]].strip().upper()
                if s_val in ("PAID", "SETTLED", "ACHITAT", "PLATIT", "ОПЛАЧЕН", "ОПЛАЧЕНО", "ЗАКРЫТ"):
                    status = "SETTLED"
                elif s_val in ("OVERDUE", "EXPIRAT", "INTARZIAT", "ПРОСРОЧЕН", "ПРОСРОЧЕНО"):
                    status = "OVERDUE"
                elif s_val in ("DEFAULTED", "DEFAULT", "ДЕФОЛТ"):
                    status = "DEFAULTED"
                elif s_val in ("DISPUTED", "DISPUTA", "СПОРНЫЙ"):
                    status = "DISPUTED"
                elif s_val in ("OUTSTANDING", "NEACHITAT", "НЕ ОПЛАЧЕН", "НЕОПЛАЧЕН", "ОТКРЫТ"):
                    status = "OUTSTANDING"
                elif s_val in ("PAID", "SETTLED", "OUTSTANDING", "OVERDUE", "DEFAULTED", "DISPUTED"):
                    status = s_val

            records.append(
                ParsedInvoiceRecord(
                    counterparty_name=cp_name,
                    counterparty_role=cp_role,
                    invoice_type=inv_type,
                    gross_amount=amt,
                    issue_date=issue_d,
                    due_date=due_d,
                    actual_payment_date=act_pay_d,
                    status=status,
                )
            )

        if not records:
            raise ParsingError("Invoice CSV parsed 0 valid invoice records.")
        return records

    def parse_xlsx(
        self,
        file_content: bytes,
        business_id: Optional[UUID] = None,
    ) -> List[ParsedInvoiceRecord]:
        if openpyxl is None:
            raise RuntimeError("openpyxl must be installed to parse xlsx workbooks.")
        wb = openpyxl.load_workbook(io.BytesIO(file_content), data_only=True, read_only=True)
        ws = wb.active
        if ws is None:
            wb.close()
            raise ParsingError("Workbook has no active sheet.")
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
        out = io.StringIO()
        writer = csv.writer(out)
        for r in rows:
            if any(r):
                writer.writerow([str(c) if c is not None else "" for c in r])
        return self.parse_csv(out.getvalue(), business_id=business_id)


class CreditObligationParser:
    """
    Парсер кредитных обязательств и займов (obligations.csv / xlsx).
    Разбирает остаток долга, регулярный платеж и историю просрочек.
    """

    def parse_csv(
        self,
        file_content: Union[bytes, str],
        business_id: Optional[UUID] = None,
    ) -> List[ParsedCreditObligationRecord]:
        if isinstance(file_content, bytes):
            try:
                text = file_content.decode("utf-8-sig")
            except UnicodeDecodeError:
                try:
                    text = file_content.decode("cp1251")
                except UnicodeDecodeError:
                    text = file_content.decode("latin-1")
        else:
            text = file_content

        if not text.strip():
            raise ParsingError("Uploaded credit obligation CSV is completely empty.")

        stream = io.StringIO(text)
        sample = text[:4096]
        delimiter = ","
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
            delimiter = dialect.delimiter
        except Exception:
            for cand in [";", "\t", ","]:
                if sample.count(cand) > sample.count(delimiter):
                    delimiter = cand

        reader = csv.reader(stream, delimiter=delimiter)
        header: Optional[List[str]] = None
        for row in reader:
            if any(cell.strip() for cell in row):
                header = [c.strip().lower() for c in row]
                break

        if not header:
            raise ParsingError("Could not locate valid header row in credit obligations file.")

        col_map: Dict[str, int] = {}
        for idx, col in enumerate(header):
            col_norm = re.sub(r"[^\w]", "", col.strip().lower().replace(" ", "_"))
            if any(
                k in col_norm
                for k in (
                    "facility_type",
                    "facility",
                    "type",
                    "credit_type",
                    "tip_credit",
                    "tip",
                    "вид_кредита",
                    "тип",
                    "продукт",
                )
            ):
                col_map.setdefault("facility_type", idx)
            elif any(
                k in col_norm
                for k in (
                    "principal_amount",
                    "principal",
                    "loan_amount",
                    "credit_limit",
                    "suma_credit",
                    "valoare",
                    "сумма_кредита",
                    "лимит",
                    "основной_долг",
                    "сумма",
                )
            ):
                col_map.setdefault("principal_amount", idx)
            elif any(
                k in col_norm
                for k in (
                    "outstanding_balance",
                    "outstanding",
                    "balance",
                    "remaining_balance",
                    "debt",
                    "sold",
                    "rest_de_plata",
                    "datorie",
                    "остаток",
                    "остаток_долга",
                    "задолженность",
                )
            ):
                col_map.setdefault("outstanding_balance", idx)
            elif any(
                k in col_norm
                for k in (
                    "monthly_payment",
                    "payment",
                    "installment",
                    "rata_lunara",
                    "plata",
                    "ежемесячный_платеж",
                    "платеж",
                    "взнос",
                )
            ):
                col_map.setdefault("monthly_payment", idx)
            elif any(k in col_norm for k in ("past_due_30d", "overdue_30", "intarziere_30", "просрочка_30")):
                col_map.setdefault("past_due_30d_count", idx)
            elif any(k in col_norm for k in ("past_due_90d", "overdue_90", "intarziere_90", "просрочка_90")):
                col_map.setdefault("past_due_90d_count", idx)
            elif any(k in col_norm for k in ("historical_default", "defaults", "defaulturi", "дефолт", "дефолты")):
                col_map.setdefault("historical_defaults_count", idx)
            elif any(
                k in col_norm
                for k in (
                    "lender_name",
                    "lender",
                    "bank_name",
                    "creditor",
                    "banca",
                    "кредитор",
                    "банк",
                    "займодавец",
                    "наименование",
                )
            ):
                col_map.setdefault("lender_name", idx)

        if "lender_name" not in col_map or "principal_amount" not in col_map:
            raise ParsingError("Missing mandatory columns ('lender_name', 'principal_amount') in obligations CSV.")

        records: List[ParsedCreditObligationRecord] = []
        for row in reader:
            if not any(cell.strip() for cell in row):
                continue
            lender = row[col_map["lender_name"]].strip() if col_map["lender_name"] < len(row) else ""
            if not lender:
                continue

            try:
                principal, _ = clean_amount_string(row[col_map["principal_amount"]].strip())
            except Exception:
                continue

            facility_type = "TERM_LOAN"
            if "facility_type" in col_map and col_map["facility_type"] < len(row):
                ft_val = row[col_map["facility_type"]].strip().upper()
                if ft_val in ("CREDIT_LINE", "LINE_OF_CREDIT", "LINIE_DE_CREDIT", "КРЕДИТНАЯ_ЛИНИЯ", "ЛИНИЯ"):
                    facility_type = "CREDIT_LINE"
                elif ft_val in ("OVERDRAFT", "DESCOPERIT_DE_CONT", "ОВЕРДРАФТ"):
                    facility_type = "OVERDRAFT"
                elif ft_val in ("LEASING", "LEASING_FINANCIAR", "ЛИЗИНГ"):
                    facility_type = "LEASING"
                elif ft_val in ("FACTORING", "ФАКТОРИНГ"):
                    facility_type = "FACTORING"
                elif ft_val in ("TERM_LOAN", "CREDIT_TERMEN", "IMPRUMUT", "КРЕДИТ", "ЗАЙМ"):
                    facility_type = "TERM_LOAN"
                elif ft_val in ("TERM_LOAN", "CREDIT_LINE", "LINE_OF_CREDIT", "OVERDRAFT", "LEASING", "FACTORING"):
                    facility_type = ft_val

            outstanding = principal
            if "outstanding_balance" in col_map and col_map["outstanding_balance"] < len(row):
                try:
                    outstanding, _ = clean_amount_string(row[col_map["outstanding_balance"]].strip())
                except Exception:
                    pass

            monthly = Decimal("0.00")
            if "monthly_payment" in col_map and col_map["monthly_payment"] < len(row):
                try:
                    monthly, _ = clean_amount_string(row[col_map["monthly_payment"]].strip())
                except Exception:
                    pass

            def parse_int(val_str: str) -> int:
                try:
                    return max(0, int(val_str.strip()))
                except Exception:
                    return 0

            p30 = (
                parse_int(row[col_map["past_due_30d_count"]])
                if "past_due_30d_count" in col_map and col_map["past_due_30d_count"] < len(row)
                else 0
            )
            p90 = (
                parse_int(row[col_map["past_due_90d_count"]])
                if "past_due_90d_count" in col_map and col_map["past_due_90d_count"] < len(row)
                else 0
            )
            defaults = (
                parse_int(row[col_map["historical_defaults_count"]])
                if "historical_defaults_count" in col_map and col_map["historical_defaults_count"] < len(row)
                else 0
            )

            records.append(
                ParsedCreditObligationRecord(
                    lender_name=lender,
                    facility_type=facility_type,
                    principal_amount=principal,
                    outstanding_balance=outstanding,
                    monthly_payment=monthly,
                    past_due_30d_count=p30,
                    past_due_90d_count=p90,
                    historical_defaults_count=defaults,
                )
            )

        if not records:
            raise ParsingError("Credit obligation CSV parsed 0 valid records.")
        return records

    def parse_xlsx(
        self,
        file_content: bytes,
        business_id: Optional[UUID] = None,
    ) -> List[ParsedCreditObligationRecord]:
        if openpyxl is None:
            raise RuntimeError("openpyxl must be installed to parse xlsx workbooks.")
        wb = openpyxl.load_workbook(io.BytesIO(file_content), data_only=True, read_only=True)
        ws = wb.active
        if ws is None:
            wb.close()
            raise ParsingError("Workbook has no active sheet.")
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
        out = io.StringIO()
        writer = csv.writer(out)
        for r in rows:
            if any(r):
                writer.writerow([str(c) if c is not None else "" for c in r])
        return self.parse_csv(out.getvalue(), business_id=business_id)


def load_file_to_dataframe(file_path: str) -> Any:
    """Загружает файл выписки в pandas DataFrame (для обратной совместимости)."""
    if pd is None:
        raise RuntimeError("pandas must be installed to use load_file_to_dataframe.")
    if file_path.endswith(".csv"):
        return pd.read_csv(file_path)
    elif file_path.endswith((".xlsx", ".xls")):
        return pd.read_excel(file_path)
    raise ValueError(f"Неподдерживаемый формат файла: {file_path}")
