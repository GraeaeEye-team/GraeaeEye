"""
Tests for all format extractors (CSV, Excel, JSON, XML, Text/PDF).
"""

import json
from pathlib import Path
import pytest
import openpyxl

from smart_credit_parser.extractors import (
    CSVExtractor,
    ExcelExtractor,
    JSONExtractor,
    XMLExtractor,
    TextExtractor,
    get_extractor_for_file,
)


def test_csv_extractor_comma(tmp_path: Path):
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("id,name,amount\n1,Alpha,100.50\n2,Beta,200.75\n", encoding="utf-8")

    extractor = get_extractor_for_file(csv_file)
    assert isinstance(extractor, CSVExtractor)

    headers, sample = extractor.get_sample(csv_file)
    assert headers == ["id", "name", "amount"]
    assert len(sample) == 2
    assert sample[0] == {"id": "1", "name": "Alpha", "amount": "100.50"}

    all_rows = extractor.extract_all(csv_file)
    assert len(all_rows) == 2


def test_csv_extractor_semicolon_cp1251(tmp_path: Path):
    csv_file = tmp_path / "test_ru.csv"
    content = "ИНН;Название;Сумма\n1002600001;Тест SRL;1250,50\n"
    csv_file.write_bytes(content.encode("cp1251"))

    extractor = get_extractor_for_file(csv_file)
    assert isinstance(extractor, CSVExtractor)

    headers, sample = extractor.get_sample(csv_file)
    assert headers == ["ИНН", "Название", "Сумма"]
    assert sample[0]["ИНН"] == "1002600001"
    assert sample[0]["Название"] == "Тест SRL"


def test_excel_extractor(tmp_path: Path):
    xlsx_file = tmp_path / "test.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["invoice_no", "date", "total"])
    ws.append(["INV-101", "2025-01-15", 4500.0])
    ws.append(["INV-102", "2025-01-16", 8900.5])
    wb.save(xlsx_file)

    extractor = get_extractor_for_file(xlsx_file)
    assert isinstance(extractor, ExcelExtractor)

    headers, sample = extractor.get_sample(xlsx_file)
    assert headers == ["invoice_no", "date", "total"]
    assert len(sample) == 2
    assert sample[0]["invoice_no"] == "INV-101"
    assert float(sample[0]["total"]) == 4500.0
    assert float(sample[1]["total"]) == 8900.5


def test_json_extractor_array(tmp_path: Path):
    json_file = tmp_path / "test.json"
    data = [
        {"account_number": "ACC-01", "balance": 15000},
        {"account_number": "ACC-02", "balance": 32000},
    ]
    json_file.write_text(json.dumps(data), encoding="utf-8")

    extractor = get_extractor_for_file(json_file)
    assert isinstance(extractor, JSONExtractor)

    headers, sample = extractor.get_sample(json_file)
    assert "account_number" in headers
    assert "balance" in headers
    assert len(sample) == 2


def test_json_extractor_wrapped_and_jsonl(tmp_path: Path):
    # Wrapped in dict
    json_file = tmp_path / "wrapped.json"
    json_file.write_text(json.dumps({"records": [{"a": 1}, {"a": 2}]}), encoding="utf-8")
    extractor = JSONExtractor()
    headers, sample = extractor.get_sample(json_file)
    assert headers == ["a"]
    assert len(sample) == 2

    # JSONL
    jsonl_file = tmp_path / "test.jsonl"
    jsonl_file.write_text('{"x": "foo"}\n{"x": "bar"}\n', encoding="utf-8")
    headers, sample = extractor.get_sample(jsonl_file)
    assert headers == ["x"]
    assert len(sample) == 2


def test_xml_extractor(tmp_path: Path):
    xml_file = tmp_path / "test.xml"
    content = """<?xml version="1.0" encoding="utf-8"?>
<Invoices>
    <Invoice id="INV-1">
        <GrossAmount>5000.00</GrossAmount>
        <Status>PAID</Status>
    </Invoice>
    <Invoice id="INV-2">
        <GrossAmount>1200.00</GrossAmount>
        <Status>OVERDUE</Status>
    </Invoice>
</Invoices>
"""
    xml_file.write_text(content, encoding="utf-8")

    extractor = get_extractor_for_file(xml_file)
    assert isinstance(extractor, XMLExtractor)

    headers, sample = extractor.get_sample(xml_file)
    assert "GrossAmount" in headers
    assert "Status" in headers
    assert len(sample) == 2
    assert sample[0]["GrossAmount"] == "5000.00"
    assert sample[0]["Status"] == "PAID"


def test_text_extractor_key_value(tmp_path: Path):
    txt_file = tmp_path / "statement.txt"
    content = """
Company Name: MoldAgro SRL
Fiscal Code: 1002600004567
Sector: Agriculture
---
Company Name: NordTrans SRL
Fiscal Code: 1002600008910
Sector: Logistics
"""
    txt_file.write_text(content, encoding="utf-8")

    extractor = get_extractor_for_file(txt_file)
    assert isinstance(extractor, TextExtractor)

    headers, sample = extractor.get_sample(txt_file)
    assert "Company Name" in headers
    assert "Fiscal Code" in headers
    assert len(sample) == 2
    assert sample[0]["Company Name"] == "MoldAgro SRL"
    assert sample[1]["Fiscal Code"] == "1002600008910"
