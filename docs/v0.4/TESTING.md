# Тестирование MOEX Intelligence v0.4.0

Проверки выполнены 25 октября 2026 года. JSON timestamps — UTC. Среда: Linux x86_64, Python 3.12.14; это не физический Mac. Доказательства v0.3 находятся отдельно в `v0.3/`.

| Проверка | Результат | Доказательство |
|---|---|---|
| v0.3 до изменений | 75 passed | `v0.3/baseline-v0.4.txt` |
| Финальный автоматический набор | **105 passed**, без пропусков | `test-results.xml`, `unit-test-summary.txt` |
| Чистая установка v0.4 | Новый venv, установка с SHA-256 и повторно 105 passed | `clean-install.log`, `clean-test-summary.txt` |
| Зависимости | Совместимы; locks не изменялись | `dependencies-check.txt`; ARM64 resolver предыдущей версии в v0.3 |
| MCP stdio | 15 инструментов, прежние 13 сохранены; demo/advisor/backtest/report/error | `tests/test_mcp_protocol.py` |
| MCP HTTP | health/15 tools/demo/invalid ticker; чужой Host → 421 | `http-verification.json` |
| Live SBER Advisor | Реальная история, профиль 5000 ₽/12 мес/5%/low; конфликт допустимого риска выявлен | `advisor-live.json`, `advisor-live.log`, `SBER_example_report.md` |
| Live IMOEX и сравнение с SBMX | Индекс в пунктах, пересечение общих дат, без подмены демо | `advisor-live.json` |
| Streamlit AppTest | 9 страниц/расчёты, нет fallback, история; переключение режима сохраняет числа | `tests/test_dashboard.py` |
| Chromium | 9 страниц, 10000 сценариев, бэктест, отчёт, депозит, Advisor, история, настройки; 0 page errors | `ui/verification.json`, `browser-test.log` |
| Визуальная проверка | Просмотрены скриншоты; исправлены верхний отступ и пояснения | `ui/overview.png`, `ui/advisor.png`, `ui/time-machine-chart.png`, `ui/strategy-lab.png` |
| Launcher | Занятый 8501 → 8502, повторный старт, неверный токен отвергнут, собственный child остановлен, повторный stop | `launcher-verification.json` |
| Shell-скрипты | `bash -n` успешно | `shell-check.txt` |

## Сценарии Advisor из задания

1. Лимит просадки 5% при большем наблюдаемом риске → unsuitable, даже при положительной доходности.
2. Короткая история → insufficient, балл отсутствует.
3. Покупка увеличивает концентрацию → обязательный конфликт.
4. Расхождение моделей >5 п.п. → явная неопределённость, не выбор красивой модели.
5. Сбой MOEX → ошибка; demo не включается автоматически.
6. Нет полного профиля → личное соответствие не оценено.
7. Сильный исторический рост без фундаментальной оценки → study, не положительный сигнал.

Дополнительно: долгий срок не сокращается скрыто; stale/invalid/bond данные не создают уверенного вывода; воспроизводимость моделей и вердикта; точная формула остатка/лотов; existing cash не прибавляется повторно; GBM не делает двойную поправку drift; снимок не меняется вслед за исходным объектом и проверяется на повреждение; секреты не попадают в preferences. Тесты приоритета правил проверяют missing-profile, конфликт при одновременно отсутствующих данных и верхнюю границу балла при недостатке денег на лот. Сравнение инструментов проверено на общих датах, beta=1 для пропорциональных рядов и отклонении облигаций/FX.

Сохранённые регрессионные тесты покрывают повторы/пагинацию/кеш MOEX, схемы таблиц и ошибочные цены; точные VaR/ES, комиссии и перескок стопа; следующий OPEN и причинность сигналов SMA/EMA/RSI/custom; журнал и денежные потоки/TWR; реальные протоколы MCP. Старые 15 тестов Reader продолжают проходить.

## Как повторить

```bash
.venv/bin/python -m pip install --require-hashes -r requirements-dev.txt
.venv/bin/python -m pytest -q --junitxml=docs/test-results.xml
.venv/bin/python -m scripts.verify_http
.venv/bin/python -m scripts.verify_advisor_live
```

Live-скрипт требует доступный ISS и не переключается на демо. Optional browser QA: установите Playwright 1.51.0 в отдельный venv и Chromium headless shell; запустите `MOEX_APP_PYTHON=/absolute/project/.venv/bin/python /absolute/browser-venv/bin/python scripts/verify_browser.py`. QA-пакеты не нужны обычному пользователю. Сборка архива: `python -m scripts.package_release`.

## Что не проверено

Finder, Gatekeeper, Safari, запуск на физическом Apple Silicon и Python 3.13. Нет возможности воспроизвести VPN пользователя; недоступность ISS проверена через контролируемую ошибку. Все инструменты/режимы/корпоративные действия MOEX не перебирались. Live-проверка подтверждает получение и сквозной расчёт, а не качество прогноза. Порогам Decision Engine не приписывается эмпирическая финансовая валидация. Положительная категория consider существует в контракте, но сквозной Advisor не достигает её без будущего фундаментального модуля.
