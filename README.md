# Křížovky – generátor švédských křížovek

[English version](README.en.md)

Program sestaví českou **švédskou křížovku**, jakou znáte z časopisů: legendy jsou přímo v políčkách mřížky, slova vyplňují celou plochu a tajenka je v jednom až třech šedých řádcích. Zadáte velikost mřížky, text tajenky a název. Program najde slova ve vlastním slovníku (přes 110 000 českých slov), vyplní mřížku a připraví seznam slov, ke kterým je potřeba napsat legendy. Až legendy doplníte, vytvoří list k tisku (SVG a PDF) a řešení.

Hotová ukázka je ve složce [`examples/eko_krizovka/`](examples/eko_krizovka/): [křížovka k tisku](examples/eko_krizovka/puzzle.pdf) a [řešení](examples/eko_krizovka/solution.pdf). Tajenka je SLAVÍME / DEN / ZEMĚ, mřížka má 16 řádků a 12 sloupců.

## Co je potřeba

- **Python 3.10 nebo novější.** Jiné knihovny nejsou potřeba. Verzi zjistíte příkazem `python3 --version`. Program je vyzkoušený na Pythonu 3.14 v Linuxu.
- **LibreOffice**, jen pokud chcete PDF. Program si ho spouští sám (příkaz `soffice`). Bez LibreOffice dostanete křížovku jako SVG, které otevřete a vytisknete v internetovém prohlížeči.
- **Legendy** píše člověk, nebo jazykový model, například Claude. Program legendy nevymýšlí. API klíč ani připojení k internetu nepotřebuje.

## Instalace

Stáhněte si složku `krizovky` (na GitHubu tlačítko **Code → Download ZIP**, nebo zip, který jste dostali) a rozbalte ji. Všechny příkazy níže se zadávají do terminálu otevřeného v této složce.

## Příklad krok za krokem

### 1. Vygenerujte mřížku

```bash
python3 -m krizovky generate --mode swedish --size 16x12 --tajenka "SLAVÍME / DEN / ZEMĚ" \
    --title "Eko křížovka" --theme "Ochrana životního prostředí" --seed 2 --out out/den_zeme
```

- `--size 16x12` je velikost mřížky: 16 řádků, 12 sloupců.
- `--tajenka` je text, který luštitel odhalí. Lomítko `/` ho dělí na díly a každý díl dostane vlastní šedý řádek.
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

- **Nechte je napsat Clauda.** Pošlete mu soubor `request.json` a požádejte ho o `clues.json`. Pokyny k psaní legend (česky) i požadovaný tvar souboru jsou přímo v `request.json`. Odpověď uložte jako `out/den_zeme/clues.json`.
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

## Jak číst list

- **Legenda v políčku** patří slovu, které začíná hned vpravo od ní (vodorovně), nebo hned pod ní (svisle). Šipky list nemá.
- **Rozdělené políčko** má uprostřed vodorovnou čáru. Horní legenda patří slovu vpravo, dolní slovu dole.
- **Šedé řádky** jsou díly tajenky. Políčko před každým z nich nese popisek „1. díl tajenky“, „2. díl tajenky“ atd., u jednodílné tajenky jen „tajenka“. Pod mřížkou jsou okénka, kam se tajenka zapíše.
- **Černý kotouč ●** označuje políčko bez písmene i bez legendy.
- **Pomůcka:** pod mřížkou vypisuje slova, která luštitel nemusí znát.

## Co hlídat před tiskem

- Slovník je sestavený strojově. Nářeční tvary, neznámá jména, slangová slova bez vysvětlení, nadávky a vulgarismy jsou z něj vyřazené, přesto do mřížky občas projde slovo vzácné nebo zastaralé (v ukázce třeba SOC nebo MANĚ). Před tiskem projděte všechna slova i legendy. Když se vám některé slovo nelíbí, vygenerujte mřížku znovu s jiným `--seed`.
- Dlouhé legendy se v políčku zalamují podle slabik, ale jen jednoduchým pravidlem bez slovníku (CITOSLOV-CE); u cizích slov a složenin se dělení může splést.
- Díly tajenky nezabírají celý řádek a políčka s legendami jsou rozmístěná volněji než v časopisech.
- Legendy, které napíše jazykový model, mohou obsahovat chybu. Zkontrolujte je.

## Autor a licence

Autor: Michal Stasiak, 2026.

- Program je pod licencí MIT ([LICENSE](LICENSE)). Smíte ho volně používat, upravovat a šířit, pokud zachováte uvedení autora a text licence.
- Slovník `data/words.tsv.gz` a ukázková křížovka vycházejí z Wikislovníku a Wiktionary, a proto jsou pod licencí CC BY-SA 4.0. Při jejich šíření uveďte zdroje a zachovejte stejnou licenci. Zdroje, licence a předepsané uvedení původu jsou v [data/LICENSES.md](data/LICENSES.md).
- Vygenerované soubory `puzzle.json` a `request.json` obsahují doslovné výklady z Wikislovníku. Když je zveřejníte nebo někomu předáte, platí pro ně CC BY-SA 4.0: uveďte zdroj a zachovejte licenci. Vytištěná křížovka (SVG nebo PDF) s legendami, které jste napsali vlastními slovy, je vaše a licence slovníku se na ni nevztahuje.
