# Křížovky – generátor švédských křížovek

[English version](README.en.md)

Program sestaví českou **švédskou křížovku**, jakou znáte z časopisů: legendy jsou přímo v políčkách mřížky, slova vyplňují celou plochu a tajenka je v jednom až třech šedých řádcích. Zadáte velikost mřížky, text tajenky a název. Program najde slova ve vlastním slovníku (přes 110 000 českých slov), vyplní mřížku a připraví seznam slov, ke kterým je potřeba napsat legendy. Až legendy doplníte, vytvoří list k tisku (SVG a PDF) a řešení.

Hotová ukázka je ve složce [`examples/eko_krizovka/`](examples/eko_krizovka/): [křížovka k tisku](examples/eko_krizovka/puzzle.pdf) a [řešení](examples/eko_krizovka/solution.pdf). Tajenka je SLAVÍME / DEN / ZEMĚ, mřížka má 16 řádků a 12 sloupců.

## Rychlý start s AI agentem (doporučeno)

Program sestaví mřížku sám, legendy ale píše člověk nebo jazykový model. Nejméně práce máte, když obojí svěříte AI agentovi, který umí spouštět příkazy v terminálu, například Claude Code. Agent spustí program, napíše legendy, zkontroluje křížovku a vyrobí soubory k tisku. Vy zadáte téma a tajenku.

1. Potřebujete Python 3.10 nebo novější a AI agenta s přístupem k terminálu.
2. Rozbalte složku `krizovky` a v ní agenta spusťte (u Claude Code příkazem `claude`).
3. Vložte zadání upravené podle svého tématu. Tajenku dělte lomítkem na díly, každý díl má mít 2 až 11 písmen (při velikosti 16x12):

```text
Udělej švédskou křížovku. Postupuj podle README.md, část „Ruční postup“.
Téma: ochrana životního prostředí. Tajenka: SLAVÍME / DEN / ZEMĚ. Velikost: 16x12.
1. Vygeneruj mřížku a projdi slova v request.json. Když je mezi nimi slovo, které se
   do křížovky pro širší publikum nehodí (vulgární, nářeční, příliš odborné nebo
   zastaralé), vygeneruj mřížku znovu s jiným --seed.
   Zkus to nejvýš třikrát, pak vezmi nejlepší mřížku.
2. Napiš legendy do clues.json podle pokynů v request.json.
3. Spusť clues a validate. Když skončí chybou nebo varováním, oprav legendy.
4. Vytvoř PDF, pokud je k dispozici LibreOffice. Jinak nech SVG.
Na konci vypiš legendy, kterých si nejsi jistý, a slova, která patří do pomůcky.
```

4. Hotové soubory najdete ve složce `out/`. Před tiskem projděte všechna slova i legendy.

Postup je ověřený s Claude. S jinými modely vyzkoušený nebyl, měl by ale fungovat každý, který dobře píše česky.

**Kdo co dělá.** Agent spouští příkazy, píše legendy a hlídá chyby. Vy volíte téma a tajenku a rozhodujete, co se vytiskne. V ukázkové křížovce psal legendy model a autor ručně přepsal šest z 65.

**Bez agenta, v běžném chatu.** Mřížku vygenerujte podle části „Ruční postup“ (krok 1). Pak nahrajte `request.json` do chatu a napište: „Podle pokynů v souboru napiš clues.json. Vrať jen obsah souboru.“ Pokyny pro model (česky) i požadovaný tvar jsou přímo v `request.json`. Odpověď uložte jako `clues.json` do stejné složky a pokračujte krokem 3.

**Jak získat dobré legendy**

- Nejdřív slova, potom legendy. Nehodící se slovo vyřešíte rychleji jiným `--seed` než legendou, která ho obejde.
- Program hlídá délku legendy (nejvýš 28 znaků) a to, že neobsahuje základ slova. Srozumitelnost a výstižnost posoudí jen člověk.
- Slova, která luštitel nemusí znát, patří do `pomucka`. Vytisknou se tak, jak je napíšete, s velkými i malými písmeny.
- V `request.json` má každé slovo slovníkový výklad (`gloss`) a značky (`flags`). U několika slov výklad chybí, protože jsou jen ve frekvenčním seznamu. Jejich legenda stojí na znalostech modelu, proto je zkontrolujte.

## Co je potřeba

- **Python 3.10 nebo novější.** Jiné knihovny nejsou potřeba. Verzi zjistíte příkazem `python3 --version`. Program je vyzkoušený na Pythonu 3.14 v Linuxu.
- **LibreOffice**, jen pokud chcete PDF. Program si ho spouští sám (příkaz `soffice`). Bez LibreOffice dostanete křížovku jako SVG, které otevřete a vytisknete v internetovém prohlížeči.
- **Legendy** píše člověk, nebo jazykový model, například Claude. Program legendy nevymýšlí. API klíč ani připojení k internetu nepotřebuje.

## Instalace

Stáhněte si složku `krizovky` (na GitHubu tlačítko **Code → Download ZIP**, nebo zip, který jste dostali) a rozbalte ji. Všechny příkazy níže se zadávají do terminálu otevřeného v této složce.

## Ruční postup

Stejné kroky, které v rychlém startu dělá agent. Hodí se, když příkazy zadáváte sami.

### 1. Vygenerujte mřížku

```bash
python3 -m krizovky generate --mode swedish --size 16x12 --tajenka "SLAVÍME / DEN / ZEMĚ" \
    --title "Eko křížovka" --theme "Ochrana životního prostředí" --seed 2 --out out/den_zeme
```

- `--size 16x12` je velikost mřížky: 16 řádků, 12 sloupců.
- `--tajenka` je text, který luštitel odhalí. Lomítko `/` ho dělí na díly a každý díl dostane vlastní šedý řádek. Díl má mít aspoň 2 písmena a nejvýš o jedno méně, než má mřížka sloupců (při 12 sloupcích tedy 11). Mezery uvnitř dílu program vynechá, `V ZAHRADĚ` se vypíše jako VZAHRADĚ.
- `--title` je název nad křížovkou, `--theme` téma, které se vytiskne nad mřížku.
- `--seed 2` vybírá variantu. Jiné číslo dá jinou mřížku.
- `--out out/den_zeme` je složka, kam se výsledky uloží.

Vyplnění trvá od několika sekund do zhruba minuty. Výpis vypadá takto (seznam slov je zkrácený):

```
filled 16x12 in 4.8 s: 68 words, 3 repairs, inner blocks 17 %
puzzle_svg: out/den_zeme/puzzle.svg
solution_svg: out/den_zeme/solution.svg
solution_md: out/den_zeme/solution.md
65 clue(s) missing: PRSK, OSTROV, ROVY, SKELNÝ, PUB, TET, HALT, CO, BLÁ, … , RYSI, ONAK
Fill out/den_zeme/clues.json from out/den_zeme/request.json and run: python3 -m krizovky clues out/den_zeme
```

Program skončí kódem 3, protože chybí legendy. To je v tuto chvíli v pořádku. Ve složce je teď soubor `request.json` se seznamem slov. U každého slova je jeho význam ze slovníku a značky typu „zkratka“ nebo „zastaralé“, aby se legenda psala snáz.

### 2. Napište legendy (`clues.json`)

Legendy patří do souboru `clues.json` ve stejné složce. Možnosti jsou dvě:

- **Nechte je napsat jazykovému modelu.** Pošlete mu soubor `request.json` a požádejte ho o `clues.json`. Pokyny k psaní legend (česky) i požadovaný tvar souboru jsou přímo v `request.json`. Odpověď uložte jako `out/den_zeme/clues.json`.
- **Napište je ručně** v libovolném textovém editoru.

Soubor vypadá takto (začátek ukázky):

```json
{
 "version": 1,
 "clues": {
  "PRSK": "Citoslovce syčení kočky",
  "OSTROV": "Země obklopená vodou",
  "ROVY": "Hroby (kniž.)"
 },
 "pomucka": ["ÍHÁ", "OBMÝTNÍ", "OTKA", "PE", "SOC", "TET"]
}
```

- V `clues` je vlevo slovo z mřížky velkými písmeny, vpravo legenda. Legenda má nejvýš 28 znaků a nesmí obsahovat samotné slovo ani jeho základ.
- V `pomucka` jsou slova, která luštitel nemusí znát. Vytisknou se pod mřížkou v řádku „Pomůcka:“ přesně tak, jak je napíšete. Tento řádek je nepovinný.

Úplný `clues.json` k ukázce najdete v [`examples/eko_krizovka/clues.json`](examples/eko_krizovka/clues.json).

### 3. Vložte legendy do křížovky

```bash
python3 -m krizovky clues out/den_zeme
```

```
puzzle_svg: out/den_zeme/puzzle.svg
solution_svg: out/den_zeme/solution.svg
solution_md: out/den_zeme/solution.md
```

Program legendy zkontroluje a znovu vykreslí list. Když nějaká legenda chybí nebo obsahuje základ slova, vypíše řádek `WARNING: …` a skončí kódem 3. Legendu opravte a příkaz spusťte znovu.

Kontrolu celé křížovky (každé políčko patří do slova vodorovně i svisle, každé slovo má legendu, tajenka sedí) spustíte takto:

```bash
python3 -m krizovky validate out/den_zeme
```

```
OK: 68 entries, 12x16, mode swedish
```

Tento výpis uvádí rozměr obráceně, jako šířku × výšku (12 sloupců × 16 řádků).

### 4. PDF k tisku

Stačí přidat `--pdf`:

```bash
python3 -m krizovky clues out/den_zeme --pdf
```

Ve složce přibudou `puzzle.pdf` (křížovka) a `solution.pdf` (řešení). Bez LibreOffice otevřete `puzzle.svg` v prohlížeči a vytiskněte ho na A4. Řešení je také v textovém souboru `solution.md`.

## Běžné volby

| Volba | Co dělá |
|---|---|
| `--size 11x12` | velikost mřížky, řádky × sloupce; časopisecké rozměry jsou 11x12 a 16x12 |
| `--tajenka "A / B / C"` | tajenka; díly (v časopisech 1–3) se oddělují lomítkem |
| `--title "…"` | název nad křížovkou |
| `--theme "…"` | téma; vytiskne se nad mřížku a dostane ho i ten, kdo píše legendy |
| `--header "…"` | jiný text nad mřížku, než je téma |
| `--seed 1` | jiná varianta mřížky pro stejné zadání |
| `--timeout 300` | kolik sekund smí program hledat (výchozí hodnota je 180) |
| `--no-names` | bez vlastních jmen (měst, řek, osob) |
| `--pdf` | vytvořit i PDF (potřebuje LibreOffice) |
| `--out složka` | kam uložit výsledky |

Další dva jednodušší typy křížovek (doplňovačka s tajenkou ve sloupci a křížovka s očíslovanými legendami) a všechny volby popisuje [DEVELOPMENT.md](DEVELOPMENT.md).

## Když program skončí chybou

Číslo, kterým program skončil, zjistíte hned po příkazu přes `echo $?`.

- **Kód 3 – chybí legendy.** Nejde o chybu: doplňte `clues.json` (krok 2) a spusťte `clues`.
- **Kód 2 – mřížku se nepodařilo vyplnit.** Například:
  ```
  error: no fill of 11x12 for this tajenka within 1 s; try --timeout, a bigger grid or shorter runs
  ```
  Dejte programu víc času (`--timeout 300`), zkuste jiné `--seed`, větší mřížku nebo kratší díly tajenky. Kód 2 dostanete i při překlepu ve volbě. Program pak vypíše řádek `usage: …` a pod ním, co je špatně.
- **Kód 1 – chybné zadání.** Program vypíše řádek `error: …` s popisem, například:
  ```
  error: mode swedish draws words from the dictionary; --words is not used
  ```
  Stejný kód dostanete, když má díl tajenky jen jedno písmeno (`error: a tajenka run needs at least 2 cells, got 1`) nebo je delší, než se do mřížky vejde. Pak upravte tajenku. Kód 1 dostanete také u `--pdf`, když LibreOffice chybí nebo se nespustí (`error: soffice exited with 1: …`). SVG soubory ve složce přitom zůstanou, otevřete je v prohlížeči.

## Jak číst list

- **Legenda v políčku** patří slovu, které začíná hned vpravo od ní (vodorovně), nebo hned pod ní (svisle). Šipky list nemá.
- **Rozdělené políčko** má uprostřed vodorovnou čáru. Horní legenda patří slovu vpravo, dolní slovu dole.
- **Šedé řádky** jsou díly tajenky. Políčko před každým z nich nese popisek „1. díl tajenky“, „2. díl tajenky“ atd., u jednodílné tajenky jen „tajenka“. Pod mřížkou jsou okénka, kam se tajenka zapíše.
- **Černý kotouč ●** označuje políčko bez písmene i bez legendy.
- **Pomůcka:** pod mřížkou vypisuje slova, která luštitel nemusí znát.

## Co hlídat před tiskem

- Slovník je sestavený strojově. Nářeční tvary, neznámá jména, slangová slova bez vysvětlení, nadávky a vulgarismy jsou z něj vyřazené, přesto do mřížky občas projde slovo vzácné nebo zastaralé (v ukázce třeba SOC nebo MANĚ). Před tiskem projděte všechna slova i legendy. Když se vám některé slovo nelíbí, vygenerujte mřížku znovu s jiným `--seed`. V mřížce bývá několik zkratek a jmen; v časopisech je to běžné a legenda zkratku označí (zkr.).
- Dlouhé legendy se v políčku zalamují podle slabik, ale jen jednoduchým pravidlem bez slovníku (CITOSLOV-CE); u cizích slov a složenin se dělení může splést.
- Díly tajenky nezabírají celý řádek a políčka s legendami jsou rozmístěná volněji než v časopisech.
- Legendy, které napíše jazykový model, mohou obsahovat chybu. Zkontrolujte je.

## Autor a licence

Autor: Michal Stasiak, 2026.

- Program je pod licencí MIT ([LICENSE](LICENSE)). Smíte ho volně používat, upravovat a šířit, pokud zachováte uvedení autora a text licence.
- Slovník `data/words.tsv.gz` a ukázková křížovka vycházejí z Wikislovníku a Wiktionary, a proto jsou pod licencí CC BY-SA 4.0. Při jejich šíření uveďte zdroje a zachovejte stejnou licenci. Zdroje, licence a předepsané uvedení původu jsou v [data/LICENSES.md](data/LICENSES.md).
- Vygenerované soubory `puzzle.json` a `request.json` obsahují doslovné výklady z Wikislovníku. Když je zveřejníte nebo někomu předáte, platí pro ně CC BY-SA 4.0: uveďte zdroj a zachovejte licenci. Vytištěná křížovka (SVG nebo PDF) s legendami, které jste napsali vlastními slovy, je vaše a licence slovníku se na ni nevztahuje.
