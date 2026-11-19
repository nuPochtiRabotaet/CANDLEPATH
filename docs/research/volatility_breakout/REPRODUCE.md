# Воспроизведение Volatility Breakout на Apple Silicon

Команды рассчитаны на терминал macOS с Git и нативным CPython 3.12. При наличии Homebrew интерпретатор можно установить командой `brew install python@3.12`. Проверка на физическом Mac остаётся открытой.

Ветку клонируем в отдельный каталог, фиксируем коммит исполняемого кода, сверяем предрегистрацию и создаём временный каталог для тестов. Для сетевого режима нужен разрешённый доступ к официальному `data.binance.vision`. Торговые ключи не требуются.

```bash
(
set -eu
RUN_DIR="$(mktemp -d "${TMPDIR:-/tmp}/candlepath-breakout.XXXXXXXX")"
echo "$RUN_DIR"
git clone --single-branch --branch research/v09-volatility-breakout-1h4h \
  https://github.com/nuPochtiRabotaet/CANDLEPATH.git "$RUN_DIR/repo"
cd "$RUN_DIR/repo"
git checkout --detach 498a2ac013e798f87809c7b89a5ec3b0dca43ae2
test "$(git rev-parse HEAD)" = 498a2ac013e798f87809c7b89a5ec3b0dca43ae2
shasum -a 256 -c docs/research/volatility_breakout/SHA256SUMS
python3.12 -c 'import platform; assert platform.machine() == "arm64", platform.machine()'
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.txt
export MOEX_DATA_DIR="$RUN_DIR/isolated-data"
.venv/bin/python -m pytest -q \
  tests/test_volatility_breakout_research.py tests/test_trend_1h4h_research.py \
  tests/test_paper_path_research_v09.py tests/test_coliseum_statistics.py

set --
if [ -n "${CANDLEPATH_ARCHIVES:-}" ]; then
  set -- --archive-dir "$CANDLEPATH_ARCHIVES"
fi
if .venv/bin/python scripts/run_volatility_breakout.py "$@" --output "$RUN_DIR/first.json"; then
  .venv/bin/python scripts/run_volatility_breakout.py "$@" --output "$RUN_DIR/second.json"
  cmp "$RUN_DIR/first.json" "$RUN_DIR/second.json"
  shasum -a 256 "$RUN_DIR/first.json"
else
  status=$?
  [ ! -f "$RUN_DIR/first.json" ] || cat "$RUN_DIR/first.json"
  exit "$status"
fi
)
```

Для офлайн-запуска перед блоком команд укажите `export CANDLEPATH_ARCHIVES="/полный/путь/к/архивам"`. В папке должны находиться исходные пары `BTCUSDT-1h-YYYY-MM.zip` и `.zip.CHECKSUM`, а также такие же пары для ETHUSDT. Требуются 19 месяцев на инструмент с января 2024 по июль 2025 включительно. При отсутствии локальной копии оставьте переменную пустой для прямой загрузки. Программа сверит каждый архив с контрольной суммой издателя, затем с опубликованными ранее отпечатками всех файлов и обоих временных разрешений. Исходный manifest закреплён в SHA256SUMS. Исправление или перевыпуск архива издателем требует отдельной проверки происхождения.

Код 0 означает завершённую development-оценку. Код 2 и `status="NOT EVALUABLE"` в новом JSON означают остановку с указанной причиной. Для машинного отчёта требуется новое имя файла. Оба повторения следует выполнять с одним источником и в одной среде. В отчёте сохраняются способ доступа, версия Python и версии библиотек.

В `paths` находятся счётчики, P&L и издержки двух сценариев по отдельным периодам и суммарно. `net_return_pct` использует сумму трёх начальных капиталов (30 000 USDT), `expectancy` выражена в USDT на сделку, `win_rate` — доля от 0 до 1. В `statistics.tests` порядок восьми контрастов задаёт `statistics.columns`. Средние и границы интервалов выражены в долях начального капитала за день. Умножение на 10 000 переводит их в базисные пункты за день. В заблокированном запуске числовые результаты Breakout остаются null.
