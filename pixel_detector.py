"""Detecta marcadores quadrados na tela e, com --paint, marca um lote.

Uso: python pixel_detector.py
Área personalizada: python pixel_detector.py --pick-roi
Pintura: python pixel_detector.py --paint --limit 1
"""

from __future__ import annotations

import argparse
from collections import Counter
import ctypes
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import time
import winsound

import cv2
import numpy as np
import pyautogui
import pygetwindow


@dataclass(frozen=True)
class Square:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class Timing:
    activation: float
    movement: float
    hover: float
    sample: float
    between: float
    input_pause: float
    key_hold: float


TIMINGS = {
    "fast": Timing(0.10, 0.04, 0.08, 0.18, 0.08, 0.02, 0.05),
    "safe": Timing(0.40, 0.12, 0.30, 0.60, 0.50, 0.10, 0.12),
}


def parse_roi(value: str) -> tuple[int, int, int, int]:
    try:
        x1, y1, x2, y2 = (int(part) for part in value.split(","))
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError("Use x1,y1,x2,y2") from exc
    if x2 <= x1 or y2 <= y1:
        raise argparse.ArgumentTypeError("A área precisa ter largura e altura positivas")
    return x1, y1, x2, y2


def active_canvas_window(title_hint: str | None = None, handle: int | None = None):
    """Ativa a janela do mapa por título genérico ou identificador já capturado."""
    if handle is None and (title_hint is None or not title_hint.strip()):
        settings = Path(__file__).with_name("janela.local.json")
        if settings.is_file():
            try:
                title_hint = json.loads(settings.read_text(encoding="utf-8")).get("title_fragment", "")
            except (ValueError, AttributeError) as exc:
                raise RuntimeError("Configuração local da janela inválida") from exc
    hint = (title_hint or "").strip().casefold()
    default_hints = ("pixel art", "paint the world")

    def matches(win):
        if win.width <= 500 or win.height <= 400:
            return False
        if handle is not None:
            return getattr(win, "_hWnd", None) == handle
        title = win.title.casefold()
        return hint in title if hint else any(part in title for part in default_hints)

    windows = [
        win for win in pygetwindow.getAllWindows() if matches(win)
    ]
    if not windows:
        raise RuntimeError("Janela do mapa não encontrada. Informe parte do título dela nas configurações")
    win = max(windows, key=lambda item: item.width * item.height)
    if win.isMinimized:
        win.restore()
    win.activate()
    time.sleep(0.8)
    return win


def capture_bgr() -> np.ndarray:
    return cv2.cvtColor(np.array(pyautogui.screenshot()), cv2.COLOR_RGB2BGR)


def picker_region(image: np.ndarray) -> tuple[int, int, int, int]:
    """Faixa da barra de pintura no layout compacto ou no anterior."""
    height, width = image.shape[:2]
    top = palette_top(image)
    if top is not None and height - top < 150:
        left = max(0, width // 2 - 20)
        right = min(width, width // 2 + 400)
        return left, top, right - left, min(90, height - top)
    left = max(0, round(width * 0.04))
    top = max(0, (top if top is not None else height - 240) - 19)
    right = min(width, max(570, round(width * 0.42)))
    return left, top, right - left, min(110, height - top)


@lru_cache(maxsize=2)
def picker_template(name: str) -> np.ndarray:
    path = Path(__file__).with_name(name)
    template = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if template is None:
        raise RuntimeError(f"Arquivo do ícone do color picker ausente: {path}")
    return template


def locate_picker(image: np.ndarray, origin: tuple[int, int] = (0, 0)) -> tuple[int, int, float]:
    """Encontra o ícone do color picker na faixa capturada, sem usar posição fixa."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    best = (-1.0, 0, 0)
    for name, threshold in (("color_picker_modelo.png", 160),
                            ("color_picker_modelo_novo.png", 110)):
        mask = np.uint8(gray > threshold)
        base = np.uint8(picker_template(name) > threshold)
        for scale in (1.0, 0.9, 1.1, 0.8, 1.2):
            template = base if scale == 1.0 else cv2.resize(
                base, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
            th, tw = template.shape
            if th > mask.shape[0] or tw > mask.shape[1]:
                continue
            matches = cv2.matchTemplate(mask, template, cv2.TM_CCOEFF_NORMED)
            _, score, _, pos = cv2.minMaxLoc(matches)
            if score > best[0]:
                best = (score, origin[0] + pos[0] + tw // 2,
                        origin[1] + pos[1] + th // 2)
    score, x, y = best
    if score < 0.82:
        raise RuntimeError(
            f"Não localizei o color picker na barra da paleta (confiança {score:.2f}). "
            "Abra o modo de pintura, deixe a paleta visível e capture novamente."
        )
    return x, y, score


def locate_picker_in_screen(image: np.ndarray) -> tuple[int, int, float]:
    left, top, width, height = picker_region(image)
    return locate_picker(image[top:top + height, left:left + width], (left, top))


def palette_top(image: np.ndarray) -> int | None:
    """Acha a barra pelo color picker; usa faixas escuras apenas como reserva."""
    height, width = image.shape[:2]

    # O color picker pertence à barra e não à arte. A busca separada dos dois
    # layouts evita que uma faixa escura do mapa seja tomada pela paleta.
    for left, top, right, bottom, offset in (
        (0.50, 0.84, 0.75, 0.99, 42),  # Barra compacta, no centro.
        (0.05, 0.70, 0.35, 0.90, 35),  # Paleta antiga, à esquerda.
    ):
        x1, y1 = round(width * left), round(height * top)
        x2, y2 = round(width * right), round(height * bottom)
        try:
            _, picker_y, _ = locate_picker(image[y1:y2, x1:x2], (x1, y1))
        except RuntimeError:
            continue
        return max(0, picker_y - offset)

    min_run = max(10, round(height * 24 / 1080))

    def dark_rows(left: float, right: float) -> np.ndarray:
        band = image[:, round(width * left):round(width * right)]
        if band.size == 0:
            return np.zeros(height, dtype=bool)
        return (np.max(band, axis=2) < 85).mean(axis=1) > 0.95

    def first_run(rows: np.ndarray, start: int, end: int,
                  minimum: int = min_run) -> int | None:
        run_start = None
        for y in range(start, end):
            if rows[y] and run_start is None:
                run_start = y
            elif not rows[y] and run_start is not None:
                if y - run_start >= minimum:
                    return run_start
                run_start = None
        if run_start is not None and end - run_start >= minimum:
            return run_start
        return None

    def last_group(rows: np.ndarray, start: int, end: int) -> int | None:
        runs = []
        run_start = None
        for y in range(start, end):
            if rows[y] and run_start is None:
                run_start = y
            elif not rows[y] and run_start is not None:
                runs.append((run_start, y))
                run_start = None
        if run_start is not None:
            runs.append((run_start, end))
        gap = max(6, round(height * 15 / 1080))
        groups = []
        for left, right in runs:
            if groups and left - groups[-1][1] <= gap:
                groups[-1] = (groups[-1][0], right)
            else:
                groups.append((left, right))
        return next((left for left, right in reversed(groups)
                     if right - left >= min_run), None)

    # A paleta antiga ocupa toda a largura. A compacta fica no centro,
    # mas o botão colorido de Pintar interrompe a faixa central; por isso
    # a procuramos ligeiramente à esquerda do botão.
    middle = dark_rows(0.38, 0.42)
    wide = middle & dark_rows(0.10, 0.13) & dark_rows(0.80, 0.85)
    compact_top = last_group(middle, round(height * 0.86), round(height * 0.99))
    if compact_top is not None:
        return compact_top
    old_top = first_run(wide, round(height * 0.70), round(height * 0.88),
                        max(8, min_run // 2))
    if old_top is not None:
        return old_top
    return None


def palette_open(image: np.ndarray) -> bool:
    return palette_top(image) is not None


def auto_roi(image: np.ndarray) -> tuple[int, int, int, int]:
    height, width = image.shape[:2]
    margin_x = max(30, round(width * 0.042))
    top = max(30, round(height * 0.075))
    bar_top = palette_top(image)
    bottom = bar_top - 6 if bar_top is not None else height - max(50, round(height * 0.075))
    return margin_x, top, width - margin_x, bottom


def wait_for_f8() -> tuple[int, int]:
    vk_f8 = 0x77
    key_down = lambda: bool(ctypes.windll.user32.GetAsyncKeyState(vk_f8) & 0x8000)
    while key_down():
        time.sleep(0.03)
    while not key_down():
        time.sleep(0.03)
    point = pyautogui.position()
    while key_down():
        time.sleep(0.03)
    return int(point.x), int(point.y)


def pick_roi_f8(image: np.ndarray) -> tuple[int, int, int, int]:
    print("Mova o cursor para o primeiro canto da área e pressione F8.", flush=True)
    winsound.Beep(800, 150)
    a = wait_for_f8()
    print(f"Primeiro canto: {a}. Mova para o canto oposto e pressione F8.", flush=True)
    winsound.Beep(1000, 150)
    b = wait_for_f8()
    winsound.Beep(1200, 150)
    width, height = image.shape[1], image.shape[0]
    roi = (max(0, min(a[0], b[0])), max(0, min(a[1], b[1])),
           min(width, max(a[0], b[0])), min(height, max(a[1], b[1])))
    if roi[2] <= roi[0] or roi[3] <= roi[1]:
        raise RuntimeError("A área selecionada está vazia")
    print(f"Área selecionada: {roi}")
    return roi


def infer_pitch(values: list[int]) -> int | None:
    """Encontra o espaçamento dominante entre colunas/linhas de quadrados."""
    unique = sorted(set(values))
    differences = [b - a for a, b in zip(unique, unique[1:])]
    plausible = [value for value in differences if 8 <= value <= 60]
    if not plausible:
        return None
    return Counter(plausible).most_common(1)[0][0]


def axis_centers(values: list[int]) -> list[int]:
    """Agrupa desvios de 1–3 px do mesmo eixo da grade."""
    groups: list[list[int]] = []
    for value in sorted(set(values)):
        if not groups or value - groups[-1][-1] > 3:
            groups.append([value])
        else:
            groups[-1].append(value)
    return [int(round(np.median(group))) for group in groups]


def recover_grid_markers(crop: np.ndarray, contrast: np.ndarray,
                         roi: tuple[int, int, int, int], candidates: list[Square],
                         size: tuple[int, int]) -> list[Square]:
    """Recupera marcadores unidos a ruas, sem preencher células vazias da grade."""
    xs = axis_centers([square.x for square in candidates])
    ys = axis_centers([square.y for square in candidates])
    if len(xs) < 3 or len(ys) < 3:
        return []

    x_index = {x + delta: index for index, x in enumerate(xs) for delta in range(-3, 4)}
    y_index = {y + delta: index for index, y in enumerate(ys) for delta in range(-3, 4)}
    occupied = {(x_index.get(square.x), y_index.get(square.y)) for square in candidates}
    half_x = max(1, size[0] // 2 - 2)
    half_y = max(1, size[1] // 2 - 2)
    offset_x, offset_y = size[0] // 2 + 2, size[1] // 2 + 2
    height, width = crop.shape[:2]
    recovered: list[Square] = []

    for row, y in enumerate(ys):
        ry = y - roi[1]
        if ry - offset_y - 1 < 0 or ry + offset_y + 1 >= height:
            continue
        for column, x in enumerate(xs):
            if (column, row) in occupied:
                continue
            rx = x - roi[0]
            if rx - offset_x - 1 < 0 or rx + offset_x + 1 >= width:
                continue

            inner = crop[ry-half_y:ry+half_y+1, rx-half_x:rx+half_x+1]
            contrast_inner = contrast[ry-half_y:ry+half_y+1, rx-half_x:rx+half_x+1]
            if np.max(inner.reshape(-1, 3).std(axis=0)) > 4:
                continue
            if np.median(contrast_inner) < 12 or np.mean(contrast_inner >= 12) < 0.85:
                continue

            center = np.median(inner.reshape(-1, 3), axis=0)
            sides = (
                crop[ry-1:ry+2, rx+offset_x],
                crop[ry-1:ry+2, rx-offset_x],
                crop[ry+offset_y, rx-1:rx+2],
                crop[ry-offset_y, rx-1:rx+2],
            )
            if all(np.max(np.abs(center - np.median(side, axis=0))) >= 10 for side in sides):
                recovered.append(Square(x, y, size[0], size[1]))
    return recovered


def overlay_panel(image: np.ndarray) -> tuple[int, int, int, int] | None:
    """Localiza a janela flutuante da camada de referência."""
    height, width = image.shape[:2]
    blue, green, red = cv2.split(image)
    navy = np.uint8(
        (blue >= 85) & (blue <= 115) &
        (green >= 38) & (green <= 70) &
        (red >= 15) & (red <= 45) &
        (blue.astype(np.int16) - green.astype(np.int16) >= 25)
    )
    _, _, stats, _ = cv2.connectedComponentsWithStats(navy, 8)
    matches = []
    for x, y, box_width, box_height, area in stats[1:]:
        x, y, box_width, box_height, area = map(int, (x, y, box_width, box_height, area))
        if (x < width * 0.60 or x + box_width < width * 0.85 or
                y < height * 0.04 or y > height * 0.30 or
                box_width < max(35, width * 0.018) or
                box_height < max(50, height * 0.045) or
                area < 0.25 * box_width * box_height):
            continue

        panel = image[y:y + box_height, x:x + box_width]
        header = panel[:min(25, box_height)]
        hb, hg, hr = cv2.split(header)
        # A fileira pontilhada azul e o globo claro distinguem a janela
        # de um trecho escuro da própria arte no mapa.
        dots = ((hb > 130) & (hb.astype(np.int16) - hg.astype(np.int16) > 40) &
                (hg.astype(np.int16) - hr.astype(np.int16) > 15))
        bright = (np.min(panel, axis=2) > 130) & (np.max(panel, axis=2) - np.min(panel, axis=2) < 60)
        if np.count_nonzero(dots) < 20 or np.count_nonzero(bright) < 40:
            continue
        matches.append((area, (max(0, x - 2), max(0, y - 2),
                               min(width, x + box_width + 2), min(height, y + box_height + 2))))
    return max(matches, default=(0, None))[1]


def overlaps_box(square: Square, box: tuple[int, int, int, int] | None) -> bool:
    if box is None:
        return False
    half_width, half_height = square.width // 2, square.height // 2
    return (square.x + half_width >= box[0] and square.x - half_width < box[2] and
            square.y + half_height >= box[1] and square.y - half_height < box[3])


def detect_squares(image: np.ndarray, roi: tuple[int, int, int, int]) -> tuple[list[Square], tuple[int | None, int | None]]:
    x1, y1, x2, y2 = roi
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        raise ValueError("Área fora da imagem")

    # A camada de referência desenha um quadrado pequeno em cada pixel.
    # A mediana remove esses pontos e estima a aparência do pixel ao redor.
    background = cv2.medianBlur(crop, 25)
    contrast = np.max(cv2.absdiff(crop, background), axis=2)
    mask = np.uint8(contrast >= 12)
    _, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)

    excluded = overlay_panel(image)
    candidates: list[Square] = []
    for left, top, width, height, area in stats[1:]:
        left, top, width, height, area = map(int, (left, top, width, height, area))
        if not (4 <= width <= 16 and 4 <= height <= 16):
            continue
        if abs(width - height) > 2 or area < 0.70 * width * height:
            continue
        center_x, center_y = x1 + left + width // 2, y1 + top + height // 2
        square = Square(center_x, center_y, width, height)
        if not overlaps_box(square, excluded):
            candidates.append(square)

    if not candidates:
        return [], (None, None)

    # Mantém a dimensão típica dos marcadores. O navegador pode produzir
    # espaçamentos alternados de 21/22 px, então a fase da grade não é fixa.
    common_size = Counter((sq.width, sq.height) for sq in candidates).most_common(1)[0][0]
    candidates = [sq for sq in candidates
                  if abs(sq.width - common_size[0]) <= 1 and abs(sq.height - common_size[1]) <= 1]
    pitch_x = infer_pitch([sq.x for sq in candidates])
    pitch_y = infer_pitch([sq.y for sq in candidates])
    if pitch_x is not None and pitch_y is not None:
        candidates.extend(recover_grid_markers(crop, contrast, roi, candidates, common_size))
    candidates = [square for square in candidates if not overlaps_box(square, excluded)]
    return sorted(candidates, key=lambda sq: (sq.y, sq.x)), (pitch_x, pitch_y)


def annotated(image: np.ndarray, roi: tuple[int, int, int, int], squares: list[Square],
              picker_point: tuple[int, int] | None = None) -> np.ndarray:
    preview = image.copy()
    cv2.rectangle(preview, roi[:2], roi[2:], (0, 255, 255), 2)
    for square in squares:
        cv2.rectangle(
            preview,
            (square.x - square.width // 2, square.y - square.height // 2),
            (square.x + square.width // 2, square.y + square.height // 2),
            (0, 255, 0), 1,
        )
    excluded = overlay_panel(image)
    if excluded is not None:
        x1, y1, x2, y2 = excluded
        tint = preview.copy()
        cv2.rectangle(tint, (x1, y1), (x2, y2), (0, 0, 255), -1)
        cv2.addWeighted(tint, 0.22, preview, 0.78, 0, preview)
        cv2.rectangle(preview, (x1, y1), (x2, y2), (0, 0, 255), 2)
    if picker_point is not None:
        cv2.circle(preview, picker_point, 17, (255, 0, 255), 2)
    return preview


def paint(squares: list[Square], limit: int, timing: Timing, picker: str,
          debug_pick: Path | None, mode: str = "per_pixel",
          on_progress=None, stop_event=None,
          window_title: str | None = None, window_handle: int | None = None) -> int:
    if mode not in ("per_pixel", "specific"):
        raise ValueError("Modo de pintura desconhecido")
    target = active_canvas_window(window_title, window_handle)
    pyautogui.FAILSAFE = True  # Mova o cursor ao canto superior esquerdo para parar.
    start_image = capture_bgr()
    if not palette_open(start_image):
        raise RuntimeError("A paleta de pintura não parece estar aberta")
    current_window = overlay_panel(start_image)
    if any(overlaps_box(square, current_window) for square in squares[:limit]):
        raise RuntimeError("A janela flutuante cobre pixels da prévia. Capture novamente antes de pintar")
    region = picker_region(start_image)
    first_picker = locate_picker_in_screen(start_image) if mode == "per_pixel" and picker == "button" else None
    if mode == "per_pixel":
        print(f"Color picker: {picker}" + (f" em ({first_picker[0]}, {first_picker[1]})" if first_picker else ""))
    else:
        print("Cor específica: usando a cor já selecionada na paleta")
    print("Marcacao iniciada. Ctrl+C ou cursor no canto superior esquerdo interrompem.")
    old_pause = pyautogui.PAUSE
    pyautogui.PAUSE = timing.input_pause
    completed = 0
    try:
        for index, square in enumerate(squares[:limit], 1):
            if stop_event is not None and stop_event.is_set():
                break
            foreground = pygetwindow.getActiveWindow()
            if foreground is None or foreground._hWnd != target._hWnd:
                raise RuntimeError("A janela do mapa perdeu o foco; pintura interrompida")
            if mode == "specific":
                pyautogui.moveTo(square.x, square.y, duration=timing.movement)
                time.sleep(timing.hover)
                pyautogui.click()
                completed = index
                if on_progress is not None:
                    on_progress(index, min(limit, len(squares)))
                if index == 1 or index % 10 == 0 or index == min(limit, len(squares)):
                    print(f"{index}/{min(limit, len(squares))}: ({square.x}, {square.y})")
                time.sleep(timing.between)
                continue
            # Ativa o color picker ANTES de posicionar o mouse no quadradinho, como no
            # procedimento manual informado pelo usuario.
            if picker == "button":
                if index == 1:
                    picker_x, picker_y, _ = first_picker
                else:
                    left, top, width, height = region
                    strip = cv2.cvtColor(
                        np.array(pyautogui.screenshot(region=(left, top, width, height))),
                        cv2.COLOR_RGB2BGR,
                    )
                    picker_x, picker_y, _ = locate_picker(strip, (left, top))
                pyautogui.click(picker_x, picker_y)
            else:
                pyautogui.keyDown("i")
                try:
                    time.sleep(timing.key_hold)
                finally:
                    pyautogui.keyUp("i")
            time.sleep(timing.activation)
            pyautogui.moveTo(square.x, square.y, duration=timing.movement)
            time.sleep(timing.hover)
            pyautogui.click()  # Coleta a cor no marcador da referência.
            time.sleep(timing.sample)
            if stop_event is not None and stop_event.is_set():
                break
            if index == 1 and debug_pick:
                cv2.imwrite(str(debug_pick), capture_bgr())
                print(f"Captura após o color picker: {debug_pick.resolve()}")
            pyautogui.click()  # Marca o mesmo pixel com a cor selecionada.
            completed = index
            if on_progress is not None:
                on_progress(index, min(limit, len(squares)))
            if index == 1 or index % 10 == 0 or index == min(limit, len(squares)):
                print(f"{index}/{min(limit, len(squares))}: ({square.x}, {square.y})")
            time.sleep(timing.between)
    finally:
        pyautogui.PAUSE = old_pause
    print("Cliques concluídos. Confira o resultado no mapa.")
    return completed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, help="Analisa uma captura salva, sem clicar no site")
    parser.add_argument("--roi", type=parse_roi, help="x1,y1,x2,y2; se omitido, área automática")
    parser.add_argument("--pick-roi", action="store_true", help="Escolhe dois cantos no mapa com F8, sem abrir janela")
    parser.add_argument("--window-title", help="Parte do título da janela do mapa; omitido usa busca automática")
    parser.add_argument("--paint", action="store_true", help="Pinta após detectar; sem esta opção só gera a prévia")
    parser.add_argument("--limit", type=int, default=10, help="Máximo de pixels por execução (padrão: 10)")
    parser.add_argument("--speed", choices=TIMINGS, default="fast",
                        help="fast reduz as pausas; safe usa as pausas anteriores")
    parser.add_argument("--delay", type=float, help="Sobrescreve a pausa entre pixels, em segundos")
    parser.add_argument("--picker", choices=("button", "i"), default="button",
                        help="Como ativar o color picker (padrão: botão da paleta)")
    parser.add_argument("--sample-delay", type=float,
                        help="Sobrescreve a pausa após coletar a cor")
    parser.add_argument("--debug-pick", type=Path,
                        default=Path(__file__).with_name("apos_conta_gotas.png"),
                        help="Captura da tela após a primeira coleta")
    parser.add_argument("--preview", type=Path, default=Path(__file__).with_name("preview_pixels.png"))
    args = parser.parse_args()
    if args.limit < 1 or (args.delay is not None and args.delay < 0) or (args.sample_delay is not None and args.sample_delay < 0):
        parser.error("--limit deve ser positivo e os atrasos não podem ser negativos")
    if args.pick_roi and args.roi:
        parser.error("Use --pick-roi ou --roi, não os dois")
    if args.paint and args.image:
        parser.error("--paint requer captura ao vivo, sem --image")

    if args.image:
        image = cv2.imread(str(args.image), cv2.IMREAD_COLOR)
        if image is None:
            parser.error(f"Não consegui abrir: {args.image}")
    else:
        active_canvas_window(args.window_title)
        image = capture_bgr()
        if not palette_open(image):
            parser.error("Entre no modo de pintura e deixe a paleta aberta")

    roi = args.roi or (pick_roi_f8(image) if args.pick_roi else auto_roi(image))
    bar_top = palette_top(image)
    if not args.image and bar_top is not None and roi[3] > bar_top - 6:
        parser.error("Selecione apenas o mapa, acima da paleta")
    squares, pitch = detect_squares(image, roi)
    print(f"Encontrados {len(squares)} quadradinhos. Espaçamento estimado: {pitch} pixels.")
    cv2.imwrite(str(args.preview), annotated(image, roi, squares))
    print(f"Prévia salva em: {args.preview.resolve()}")
    if not squares:
        return
    if args.paint:
        timing = TIMINGS[args.speed]
        if args.delay is not None:
            timing = Timing(timing.activation, timing.movement, timing.hover,
                            timing.sample, args.delay, timing.input_pause, timing.key_hold)
        if args.sample_delay is not None:
            timing = Timing(timing.activation, timing.movement, timing.hover,
                            args.sample_delay, timing.between, timing.input_pause, timing.key_hold)
        paint(squares, args.limit, timing, args.picker, args.debug_pick,
              window_title=args.window_title)


if __name__ == "__main__":
    main()
