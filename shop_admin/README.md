# Shop Admin

Niezależny panel dla handlowców, który zamienia zamówienia z e-maila i Messengera w kompletne zamówienie sklepowe. Aplikacja dopasowuje klienta i produkty, sprawdza stan magazynowy, przygotowuje projekt rachunku PDF oraz szkic wiadomości do klienta.

Zamówienie i wiadomość wymagają jawnej akceptacji administratora. Shop Admin nie wysyła wiadomości do klienta automatycznie.

## Stack

- **Backend**: FastAPI + SQLAlchemy 2 (async)
- **Baza**: SQLite (development) lub PostgreSQL (produkcja)
- **Front**: Jinja2 + HTMX + Tailwind CDN
- **PDF**: ReportLab
- **Kanały**: Gmail przez adapter LedgerFlow, webhook Meta Messenger, deterministyczne mocki dla developmentu

Aplikacja działa w osobnym procesie i używa własnej bazy, katalogu plików, konfiguracji oraz sekretów. Nie modyfikuje danych ani tras głównej aplikacji LedgerFlow.

## Szybki start

Wymagany jest Python 3.12+.

```bash
cd /Users/Maciek/Projects/ledgerflow/ledgerflow

python -m venv .venv-shop-admin
source .venv-shop-admin/bin/activate
pip install -r shop_admin/requirements.txt

cp shop_admin/.env.example shop_admin/.env
python -m uvicorn shop_admin.main:app --reload --port 8001
```

Otwórz <http://localhost:8001/shop/dashboard>.

Domyślne dane developmentu:

- token administratora: `dev-admin-token`
- magazyn: `MAIN`
- klient demo: Anna Kowalska (`anna@example.pl`, PSID `demo-psid`)
- produkty demo: `KAWA-1KG`, `FILIZANKA-BIALA`, `CUKIER-1KG`

Przed środowiskiem innym niż lokalne ustaw własny `SHOP_ADMIN_SECRET_KEY` i `SHOP_ADMIN_ADMIN_TOKEN`.

## Demo

Po zalogowaniu:

1. Otwórz **Skrzynka**.
2. Kliknij **Sprawdź e-maile**, aby pobrać dwie deterministyczne wiadomości demo.
3. Pierwsza wiadomość tworzy zamówienie gotowe do zatwierdzenia.
4. Druga wiadomość zawiera niedobór magazynowy i trafia do review.
5. Kliknij **Dodaj demo Messenger**, aby sprawdzić kanał Messenger bez konta Meta.
6. Otwórz zamówienie, pobierz projekt rachunku, edytuj wiadomość, a następnie zatwierdź lub odrzuć zamówienie.

Przykładowa wiadomość e-mail:

```text
Dzień dobry, proszę przygotować zamówienie dla Anny:
2x KAWA-1KG, 3x FILIZANKA-BIALA oraz 1x CUKIER-1KG.
Magazyn: MAIN.
```

Parser obsługuje quantity + SKU/name, adres e-mail, telefon, PSID i kod magazynu. W pierwszej wersji jest to parser regułowy; interfejs `OrderParser` pozwala później podłączyć parser AI bez zmiany workflow.

## Konfiguracja

Skopiuj `shop_admin/.env.example` do `shop_admin/.env`. Wszystkie opcje mają prefiks `SHOP_ADMIN_`.

| Zmienna | Domyślnie | Zastosowanie |
|---|---|---|
| `SHOP_ADMIN_APP_ENV` | `dev` | `dev`, `test` lub `prod`; w `prod` sesja wymaga HTTPS |
| `SHOP_ADMIN_SECRET_KEY` | developmentowa | podpisywanie sesji administratora |
| `SHOP_ADMIN_ADMIN_TOKEN` | `dev-admin-token` | token logowania administratora |
| `SHOP_ADMIN_SEED_DEMO` | `true` | wstawia dane demo przy starcie |
| `SHOP_ADMIN_BASE_URL` | `http://localhost:8001` | adres aplikacji w dokumentach i linkach |
| `SHOP_ADMIN_DATABASE_URL` | SQLite w `shop_admin/data/` | URL async SQLAlchemy |
| `SHOP_ADMIN_UPLOAD_DIR` | `shop_admin/data/uploads` | katalog rachunków PDF |
| `SHOP_ADMIN_MAIL_PROVIDER` | `mock` | `mock` lub `gmail` |
| `SHOP_ADMIN_MAIL_WEBHOOK_SECRET` | developmentowy | sekret endpointu e-mail webhook |
| `SHOP_ADMIN_MESSENGER_APP_SECRET` | developmentowy | weryfikacja podpisu Meta |
| `SHOP_ADMIN_MESSENGER_VERIFY_TOKEN` | developmentowy | weryfikacja webhooka Messengera |
| `SHOP_ADMIN_DEFAULT_WAREHOUSE_CODE` | `MAIN` | magazyn używany, gdy wiadomość go nie podaje |
| `SHOP_ADMIN_PARSER_CONFIDENCE_THRESHOLD` | `0.55` | próg przejścia do automatycznego zatwierdzania |

Pełny wzór znajduje się w [`.env.example`](.env.example).

### Gmail

```env
SHOP_ADMIN_MAIL_PROVIDER=gmail
SHOP_ADMIN_GOOGLE_CLIENT_ID=...
SHOP_ADMIN_GOOGLE_CLIENT_SECRET=...
SHOP_ADMIN_GOOGLE_REFRESH_TOKEN=...
SHOP_ADMIN_GMAIL_LOOKBACK_DAYS=30
```

Adapter korzysta z istniejącego kontraktu `app.providers.mail.MailProvider` z LedgerFlow. Refresh token musi należeć do tego samego projektu Google i klienta OAuth oraz mieć zakres `https://www.googleapis.com/auth/gmail.readonly`.

### Messenger

Webhook Meta powinien wskazywać na:

```text
https://twoj-domena.pl/api/webhooks/messenger
```

Konfiguracja aplikacji wymaga:

- `SHOP_ADMIN_MESSENGER_APP_SECRET` — sekret aplikacji Meta,
- `SHOP_ADMIN_MESSENGER_VERIFY_TOKEN` — token weryfikacyjny ustawiony w panelu Meta,
- opcjonalnie `SHOP_ADMIN_MESSENGER_PAGE_TOKEN` — przygotowany pod przyszłą wysyłkę.

Podpis wiadomości jest weryfikowany z nagłówka `X-Hub-Signature-256` względem surowego body żądania. Endpoint weryfikacyjny obsługuje challenge wymagany przez Meta.

### E-mail webhook

Endpoint `/api/webhooks/email` wymaga nagłówka:

```text
X-ShopAdmin-Secret: <SHOP_ADMIN_MAIL_WEBHOOK_SECRET>
```

Może przyjąć `{ "message_id": "..." }` albo bez identyfikatora pobrać ostatnie 20 wiadomości z providerów. W production używaj losowego sekretu zapisanego w menedżerze sekretów.

## Workflow zamówienia

1. Wiadomość jest normalizowana i zapisywana z identyfikatorem providera.
2. Idempotencja `provider + external_id` blokuje duplikaty.
3. Parser wyciąga klienta, produkty, ilości i magazyn.
4. Dopasowanie klienta działa kolejno po PSID, e-mailu z treści, e-mailu nadawcy, telefonie i przybliżonej nazwie.
5. Produkty są dopasowywane po SKU, a następnie po nazwie.
6. Dostępność jest liczona jako `quantity_on_hand - reserved_quantity`.
7. Brak produktu, niejednoznaczne dane lub niedobór ustawiają status `needs_review`.
8. Zatwierdzenie rezerwuje wszystkie pozycje atomowo; odrzucenie zwalnia rezerwację.
9. Przed zatwierdzeniem powstaje PDF oznaczony jako projekt. Po zatwierdzeniu powstaje finalny rachunek.
10. Wiadomość do klienta pozostaje szkicem — użytkownik może ją edytować i skopiować, ale aplikacja jej nie wysyła.

## Interfejs

- `/shop/dashboard` — statystyki i ostatnia aktywność
- `/shop/inbox` — wiadomości, podgląd i ponawianie przetwarzania
- `/shop/orders` — lista zamówień i filtry
- `/shop/orders/{id}` — szczegóły, PDF, wiadomość, zatwierdzenie/odrzucenie
- `/shop/products` — produkty
- `/shop/warehouses` — magazyny i stany
- `/shop/customers` — klienci

Dokumentacja OpenAPI jest dostępna pod `/docs`.

## Testy

```bash
source .venv-shop-admin/bin/activate
python -m pytest shop_admin/tests -q
```

Testy pokrywają m.in. ingest e-maila, dopasowanie klienta, sumy netto/VAT/brutto, generowanie PDF, rezerwację i zwolnienie stanu, niedobory, idempotencję, retry, webhook Messengera, sekret webhooka e-mail oraz strony panelu.

## Bezpieczeństwo i ograniczenia MVP

- Trasy administratora wymagają sesji; webhooki mają osobne zabezpieczenia.
- Tokeny i sekrety muszą być zastąpione przed wdrożeniem produkcyjnym.
- W `prod` ustaw reverse proxy z HTTPS i poprawne wartości `SHOP_ADMIN_BASE_URL`.
- Treści wiadomości i załączniki są danymi niezaufanymi; nazwy plików są sanityzowane.
- Rezerwacja jest transakcyjna i wykonuje walidację całego kompletu przed aktualizacją stanów.
- Brak automatycznej wysyłki e-mail/Messenger.
- Schemat tworzy `create_all`; przed produkcją dodaj Alembic/migracje.
- Przetwarzanie działa w procesie FastAPI; przy dużym ruchu przenieś je do kolejki durable (np. Celery/Arq) i dodaj nadawanie statusów oraz monitoring retry.

## Struktura

```text
shop_admin/
├── api/             # trasy panelu i webhooków
├── providers/       # adaptery e-mail/Messenger i mocki
├── services/        # parser, matching, stock, order, invoice, message
├── templates/       # Jinja2 + HTMX
├── tests/           # workflow, stock, invoice, webhook, strony
├── config.py
├── db.py
├── main.py
├── models.py
├── seed.py
└── requirements.txt
```
