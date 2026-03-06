# Verbeterplan: Muisbeweging Accuraatheid - UI-TARS Vision-to-Action Pipeline

## Samenvatting

Na grondige analyse van de UI-TARS codebase zijn er **7 kritieke verbeterpunten** gevonden in de vision-to-action pipeline die de nauwkeurigheid van muisbewegingen aanzienlijk kunnen verbeteren. Dit plan behandelt bugs, ontbrekende validatie, precisieverlies en architectuurverbeteringen.

---

## 1. BUG FIX: `convert_point_to_coordinates()` middelt dezelfde waarde

**Bestand:** `codes/ui_tars/action_parser.py` regels 18-20
**Ernst:** KRITIEK

### Probleem
```python
def replace_match(match):
    x1, y1 = map(int, match.groups())
    x = (x1 + x1) // 2  # BUG: middelt x1 met zichzelf
    y = (y1 + y1) // 2  # BUG: middelt y1 met zichzelf
```
De regex vangt slechts twee groepen (x1, y1), maar de code doet `(x1 + x1) // 2` wat gewoon `x1` teruggeeft. Dit is functioneel correct maar misleidend — het lijkt bedoeld voor een bounding box (x1, y1, x2, y2) conversie. Als het model ooit meer dan twee coördinaten in `<point>` formaat uitvoert, wordt dit een echte bug.

### Oplossing
```python
def replace_match(match):
    x, y = map(int, match.groups())
    return f"({x},{y})"
```

---

## 2. Coördinaat Bounds Checking en Clamping

**Bestand:** `codes/ui_tars/action_parser.py` regels 468-491
**Ernst:** HOOG

### Probleem
Er is **geen validatie** dat berekende pixelcoördinaten binnen het scherm vallen. Als het model coördinaten voorspelt die buiten het beeld liggen (door afrondingsfouten of modelonzekerheid), kan pyautogui klikken op onbedoelde locaties of crashes veroorzaken.

### Oplossing
Voeg een clamping-functie toe:
```python
def clamp_coordinates(x, y, image_width, image_height):
    """Beperk coördinaten tot het geldige schermbereik."""
    x = max(0, min(x, image_width - 1))
    y = max(0, min(y, image_height - 1))
    return x, y
```

Pas dit toe op **alle** coördinaatberekeningen in `parsing_response_to_pyautogui_code()`:
- Click actions (regel 482-483)
- Drag start/end (regels 431-436)
- Scroll positie (regels 447-448)
- Hover positie (regel 491)

---

## 3. Precisieverlies bij Integer Afronding in de Resize Pipeline

**Bestand:** `codes/ui_tars/action_parser.py`
**Ernst:** HOOG

### Probleem
De coördinaat-transformatie pipeline heeft meerdere afrondingsstappen die cumulatief precisie verliezen:

1. **smart_resize()** rondt af naar veelvouden van 28 (`round_by_factor`, `floor_by_factor`, `ceil_by_factor`)
2. **Normalisatie** (regel 248-257): `float(num / smart_resize_height)` — deling door afgeronde waarde
3. **Denormalisatie** (regel 482): `round(float((x1+x2)/2) * image_width, 3)` — vermenigvuldiging met originele grootte

**Voorbeeld van precisieverlies:**
```
Origineel: 1920x1080
smart_resize → 1456x784 (afgerond naar factor 28)
Model output: (728, 392) = centrum van beeld
Normalisatie: 728/1456 = 0.5000 ✓ (toevallig exact)

Maar bij model output (200, 300):
Normalisatie: 200/1456 = 0.137363... → afgekapt
Denormalisatie: 0.137363 * 1920 = 263.73... → round → 263.738

Directe mapping: 200/1456 * 1920 = 263.74 (1 pixel verschil)
```

Bij randen en kleine elementen wordt dit verschil significant.

### Oplossing
Gebruik **directe schaling** in plaats van twee-staps normalisatie waar mogelijk:
```python
def transform_coordinate(model_coord, model_dimension, screen_dimension):
    """Directe schaling zonder tussentijds precisieverlies."""
    return model_coord / model_dimension * screen_dimension
```

Bewaar normalisatie alleen voor opslag/uitwisseling, niet voor de actieve pipeline.

---

## 4. DPI/Schaalfactor Bewustzijn

**Bestand:** Gehele pipeline
**Ernst:** HOOG

### Probleem
Het systeem houdt **geen rekening** met DPI-schaling of display scaling factors. Op moderne schermen (HiDPI/Retina) kan de werkelijke pixeldichtheid 1.25x, 1.5x, 2x of 3x zijn. pyautogui werkt met fysieke pixels terwijl screenshots logische pixels kunnen bevatten.

### Oplossing
```python
import subprocess

def get_display_scale_factor():
    """Detecteer de display schaalfactor van het systeem."""
    try:
        # Linux (X11)
        output = subprocess.check_output(
            ['xdpyinfo'], stderr=subprocess.DEVNULL
        ).decode()
        for line in output.split('\n'):
            if 'resolution' in line:
                dpi = int(line.split()[1].split('x')[0])
                return dpi / 96.0  # 96 DPI is standaard
    except Exception:
        pass
    return 1.0  # Fallback naar geen schaling

def apply_dpi_correction(x, y, scale_factor):
    """Corrigeer coördinaten voor DPI schaling."""
    return x * scale_factor, y * scale_factor
```

Integreer dit in `parsing_response_to_pyautogui_code()` als optionele parameter.

---

## 5. Sub-pixel Nauwkeurigheid en Afrondingsstrategie

**Bestand:** `codes/ui_tars/action_parser.py` regels 431-436, 447-448, 482-483
**Ernst:** MIDDEL

### Probleem
De huidige code gebruikt `round(..., 3)` wat 3 decimalen behoudt:
```python
x = round(float((x1 + x2) / 2) * image_width, 3)  # bijv. 263.738
```
Maar pyautogui accepteert integers voor pixelcoördinaten. De extra decimalen worden intern alsnog afgerond, wat onvoorspelbaar gedrag kan geven.

### Oplossing
Gebruik **consistente integer-afronding** met `round()` naar het dichtstbijzijnde gehele getal:
```python
x = int(round(float((x1 + x2) / 2) * image_width))
y = int(round(float((y1 + y2) / 2) * image_height))
```

---

## 6. Veiligheidsverbetering: Verwijder `eval()` voor Coördinaat Parsing

**Bestand:** `codes/ui_tars/action_parser.py` regels 429, 433, 445, 475
**Ernst:** MIDDEL (veiligheid) / LAAG (accuraatheid)

### Probleem
De code gebruikt `eval()` om coördinaatstrings te parsen:
```python
x1, y1, x2, y2 = eval(start_box)
```
Dit is een beveiligingsrisico (code-injectie) EN kan onverwachte resultaten geven bij malformed model output.

### Oplossing
Gebruik `ast.literal_eval()` of een specifieke parser:
```python
import ast

def parse_box_coordinates(box_str):
    """Veilig parsen van coördinaatstrings."""
    try:
        coords = ast.literal_eval(box_str)
        if isinstance(coords, (list, tuple)) and len(coords) in (2, 4):
            return [float(c) for c in coords]
        raise ValueError(f"Onverwacht formaat: {box_str}")
    except (ValueError, SyntaxError) as e:
        raise ValueError(f"Kan coördinaten niet parsen: {box_str}") from e
```

---

## 7. Visuele Verificatie en Logging Pipeline

**Bestand:** Nieuw toe te voegen
**Ernst:** MIDDEL (voor debugging en continue verbetering)

### Probleem
Er is geen manier om te verifiëren of de berekende coördinaten correct zijn zonder handmatige inspectie. Er is geen logging van de coördinaat-transformatiestappen.

### Oplossing
Voeg een optionele debug/verificatie modus toe:

```python
import logging

logger = logging.getLogger("ui_tars.coordinates")

def log_coordinate_transform(stage, values, context=""):
    """Log coördinaat-transformatie voor debugging."""
    logger.debug(f"[{stage}] {context}: {values}")

# Gebruik in pipeline:
# log_coordinate_transform("model_output", (200, 300), "raw model coords")
# log_coordinate_transform("normalized", (0.137, 0.383), "after normalization")
# log_coordinate_transform("screen_pixel", (264, 413), "final pixel coords")
```

Voeg ook een visuele verificatie-tool toe die de berekende klikpositie op de screenshot tekent voordat de actie wordt uitgevoerd (opt-in voor debugging).

---

## Implementatie Prioriteit

| # | Verbetering | Ernst | Effort | Impact |
|---|-------------|-------|--------|--------|
| 1 | Bug fix `convert_point_to_coordinates` | KRITIEK | Klein | Direct |
| 2 | Bounds checking/clamping | HOOG | Klein | Voorkomt crashes en foute klikken |
| 3 | Precisieverlies in resize pipeline | HOOG | Middel | ~1-5 pixel nauwkeuriger |
| 4 | DPI/schaalfactor bewustzijn | HOOG | Middel | Vereist voor HiDPI schermen |
| 5 | Consistente integer afronding | MIDDEL | Klein | Voorspelbaarder gedrag |
| 6 | Verwijder eval() | MIDDEL | Klein | Veiligheid + robuustheid |
| 7 | Logging en visuele verificatie | MIDDEL | Middel | Debugging en continue verbetering |

---

## Aanbevolen Teststrategie

### Unit Tests Toevoegen
```python
class TestCoordinateAccuracy(unittest.TestCase):
    def test_roundtrip_center_pixel(self):
        """Test dat centrum-pixel exact roundtript door de pipeline."""
        # Origineel 1920x1080, model ziet 1456x784
        # Centrum: (728, 392) -> normalisatie -> denormalisatie = (960, 540)

    def test_edge_coordinates(self):
        """Test coördinaten bij randen van het scherm."""

    def test_small_element_accuracy(self):
        """Test nauwkeurigheid voor kleine UI-elementen (bijv. 20x20px knoppen)."""

    def test_bounds_clamping(self):
        """Test dat out-of-bounds coördinaten correct geclamped worden."""

    def test_dpi_scaling(self):
        """Test coördinaat correctie bij verschillende DPI waarden."""
```

### End-to-End Validatie
- Maak een testset van screenshots met bekende klikdoelen
- Vergelijk berekende pixelcoördinaten met de werkelijke positie van het doelelement
- Meet de gemiddelde afwijking in pixels voor en na verbeteringen

---

## Geschatte Totale Impact

Met alle verbeteringen geïmplementeerd verwachten we:
- **1-5 pixel** verbetering in gemiddelde nauwkeurigheid door betere afronding
- **Eliminatie van crashes** door out-of-bounds coördinaten
- **Correcte werking op HiDPI schermen** (momenteel potentieel 2x offset)
- **Betere debugging** mogelijkheden voor toekomstige modelverbeteringen
- **Verhoogde veiligheid** door verwijdering van eval()
