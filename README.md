# Deal Watcher

Skript, ktorý sleduje výpredajové stránky, filtruje produkty podľa značky a
minimálnej zľavy, a nové nálezy posiela ako Telegram správu. Beží zadarmo cez
GitHub Actions - nepotrebuješ mať zapnutý vlastný počítač.

## 1. Vytvor si Telegram bota (5 minút)

1. V Telegrame nájdi **@BotFather**, napíš mu `/newbot` a postupuj podľa
   pokynov (zvoľ meno a username bota).
2. BotFather ti dá **token** v tvare `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxx`.
   Ten si ulož.
3. Napíš svojmu novému botovi akúkoľvek správu (napr. "ahoj"), aby si s ním
   začal konverzáciu.
4. Otvor v prehliadači (nahraď `<TOKEN>` svojím tokenom):
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   V odpovedi nájdeš `"chat":{"id": 123456789, ...}` - toto číslo je tvoje
   **chat_id**.

## 2. Vytvor GitHub repozitár

1. Na GitHube vytvor nový repozitár - **odporúčam verejný (public)**. Pri
   verejných repozitároch sú GitHub Actions minúty zdarma bez limitu. Pri
   súkromnom (private) repozitári má free plán limit len 2000 minút mesačne,
   čo pri behu každých 5 minút nestačí (vyšlo by to na tisícky minút mesačne).
2. Nahraj doň všetky súbory z tohto priečinka (zachovaj štruktúru vrátane
   `.github/workflows/watch.yml`).

## 3. Pridaj Telegram údaje ako GitHub Secrets

V repozitári choď na **Settings → Secrets and variables → Actions → New
repository secret** a pridaj:

- `TELEGRAM_BOT_TOKEN` - token z kroku 1
- `TELEGRAM_CHAT_ID` - chat_id z kroku 1

## 4. Zapni Actions

Choď na záložku **Actions** v repozitári, potvrď povolenie workflowov (GitHub
to pri prvom repozitári zvykne vyžadovať) a skús ho spustiť ručne cez
**Run workflow**, aby si overil, že funguje. Potom už pobeží automaticky
podľa plánu (`*/5 * * * *` = každých 5 minút).

## 5. Uprav si config.yaml

Otvor `config.yaml` a nastav si:

- `min_discount_percent` - od akej výšky zľavy chceš dostávať upozornenia
- `brands` - zoznam značiek (prázdny zoznam `[]` = hlásiť všetko)
- `sites` - ktoré stránky sa majú kontrolovať (zapni/vypni cez `enabled`)

## Dôležité obmedzenia, o ktorých treba vedieť

- **GitHub scheduled workflows sa po 60 dňoch bez aktivity v repozitári
  automaticky vypnú.** Ak repozitár dlho nepoužívaš, treba workflow znova
  ručne spustiť/potvrdiť.
- **"Každých 5 minút" je maximum, nie záruka.** Pri vyššom zaťažení GitHubu
  môže byť spustenie o pár minút neskôr - to je normálne pri zdarma dostupných
  Actions.
- **ASOS a Zalando Lounge tu zámerne nie sú.** Majú silnú ochranu proti
  automatizovanému čítaniu stránky (a Zalando Lounge navyše vyžaduje
  prihlásenie), takže jednoduchý bezplatný scraper by sa tam neustále
  blokoval. Pre tieto konkrétne obchody je spoľahlivejšie prihlásiť sa na ich
  vlastný newsletter/appku - notifikácie odtiaľ robia presne to isté, len to
  robí priamo obchod.
- **Over si podmienky používania (ToS) každého webu, ktorý pridáš.**
  Automatizované sťahovanie stránky nemusí byť všade formálne povolené, aj
  keď je technicky možné. Skript je nastavený na šetrné, nízkofrekvenčné
  dopyty pre osobné použitie (kontrola raz za pár minút, jeden request na
  stránku) - nie na masové sťahovanie dát.

## Pridanie nového webu

1. Otvor si cieľovú stránku vo výpredaji, klikni pravým tlačidlom na jeden
   produkt → **Preskúmať / Inspect** a nájdi, aký HTML element sa opakuje pre
   každý produkt (napr. `<li class="product-item">`).
2. Zisti, kde presne je v texte cena, pôvodná cena a percento zľavy.
3. Vo `watcher.py` napíš novú funkciu `parse_meno_webu(html, base_url)`
   podľa vzoru `parse_8a_style` - musí vrátiť zoznam slovníkov s kľúčmi
   `name`, `url`, `price`, `rrp`, `discount`.
4. Zaregistruj ju do slovníka `PARSERS` na konci sekcie s parsermi.
5. Pridaj stránku do `config.yaml` s príslušným `parser:` menom.

Stránky založené na tej istej platforme (napr. 8a.sk/8a.cz/8a.pl) môžu zdieľať
jeden parser - stačí zmeniť len `url`.
