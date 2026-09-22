# Тестовый набор данных: VICTORIA AGRO-EXPORT SRL (`test_data2`)

Данный набор данных специально сформирован и протестирован для гарантированного прохождения через конвейер инжестии (`IngestionPipeline`) и всех 9 аналитических модулей скоринга (`UnderwritingAnalyticalPipeline`).

---

## 1. Реквизиты для формы ввода (Enterprise Underwriting)

При заполнении формы в веб-интерфейсе укажите следующие данные:

* **Company Legal Name \***: `VICTORIA AGRO-EXPORT SRL`
* **National Tax ID (IDNO) \***: `1003600024881`
* **Industry Classification (NACE/CAEM) \***: `G46`

---

## 2. Файлы для загрузки в дропзоны UI

В форме расположены 3 блока загрузки файлов:

| Дропзона в UI | Файл из `data/test_data2/` | Обязательность | Содержимое |
| :--- | :--- | :---: | :--- |
| **Bank Statement Ledger** | [`transactions.csv`](./transactions.csv) | **REQUIRED** | 49 банковских проводок за 12 месяцев (поступления выручки от розничных сетей, зарплаты, налоги, погашение кредитов, расчеты с поставщиками). |
| **Commercial Invoices** | [`invoices.csv`](./invoices.csv) | **OPTIONAL** | 19 счетов-фактур (дебиторка от Metro, Linella, Kaufland; кредиторка перед поставщиками удобрений и топлива AgroChim, Lukoil, EcoPackaging). |
| **Credit Obligations** | [`obligations.csv`](./obligations.csv) | **OPTIONAL** | 3 кредитных обязательства (инвестиционный кредит в maib, кредитная линия в Victoriabank, лизинг техники в OTP Bank Mobiasbanca). |

---

## 3. Дополнительные файлы профиля компании

Используются при сидировании базы данных или для расширенной аналитики:

* [`business.csv`](./business.csv) — карточка предприятия (дата регистрации, совет директоров, независимые члены).
* [`accounts.csv`](./accounts.csv) — текущий операционный баланс и лимит овердрафта в MDL.
* [`shareholders.csv`](./shareholders.csv) — структура бенефициарного владения (Victor Ceban 45%, Natalia Moraru 35%, AgroInvest Capital 20%).

---

## 4. Ожидаемые результаты андеррайтинга

* **Статус всех 9 субмодулей**: `SUCCESS` (100% расчет метрик OS, WPR, MSR, CD, SD, ICR, CFS, RQ, ICDL).
* **Скор привлекательности (Investment Score)**: ~62.25 / 100
* **Вероятность дефолта (PD)**: ~26.5%
* **Вердикт**: `MODERATE_MONITORED` (Умеренный риск, устойчивый денежный поток, рекомендация кредитному комитету: `MANUAL_REVIEW` с лимитом).

