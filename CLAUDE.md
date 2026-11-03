# CLAUDE.md — контекст проекта

Decky Loader плагин «Custom Games» для Steam Game Mode на Linux (проверялся на Ubuntu 26.04 + gamescope-session, Decky 3.3.1).
Сторонние игры: сам находит, добавляет в Steam без перезапуска, ставит официальные обложки Steam и держит все картинки библиотеки в нужном размере (меньше — апскейл на GPU, больше — уменьшение на canvas во фронтенде), заполняет вкладки страницы игры данными настоящей игры из Steam.
Прототип внешнего вида — `mockups/`.

## Структура
- `main.py` — бэкенд Decky (класс `Plugin`), настройки `settings.json`, привязки `games.json` (appid ярлыка → Steam AppID и источник), хэши картинок `artwork.json`.
- `py_modules/customgames/` — без зависимостей от Decky, только стандартная библиотека:
  - `steamenv.py` — корень Steam, активный пользователь (loginusers.vdf), библиотеки, бинарный `shortcuts.vdf`, grid, префиксы Proton
  - `sources.py` — папки с играми и `library.json` Anker Launcher; игры из `steamapps/common` пропускаются; «уже в Steam» = exe ярлыка внутри папки игры; `game_root` перешагивает контейнеры (AnkerGames/Games)
  - `exepick.py` — выбор exe (корневой > Shipping, Vulkan-сборка, без redist/crash/кряков)
  - `appid.py` — AppID из `steam_appid.txt` / `steam_emu.ini` / конфигов эмуляторов, из папок сохранений эмуляторов в префиксе (`GSE Saves/<id>`, `RUNE/<id>`…); 480 (Spacewar) игнорируется
  - `store.py` — поиск в магазине по названию (только точное совпадение после нормализации), appdetails, схема достижений (`IPlayerService/GetGameAchievements` без ключа)
  - `artwork.py` — манифест хэшей, очередь up/down (цели: портрет 1200×1800, широкая 1840×860, hero 5760×1860, логотип 1000–2400 по ширине), официальные картинки Steam для новых игр. SteamGridDB и коллекцию пользователь убрал намеренно: SteamGridDB он использует отдельным плагином, а у Steam уже есть свой фильтр сторонних игр
  - `upscaler.py` — upscayl-bin (Real-ESRGAN, ncnn/Vulkan): скачивается самим плагином при первом запуске (`_install_deps`, статус в `get_state().deps`, повтор кнопкой «Установить зависимости»), SHA-256 закреплены; один вызов делает x4 + точный размер + JPEG
  - `achievements.py` — прогресс из `achievements.json` (GSE) и `achievements.ini` (RUNE/CODEX)
- `src/` — фронтенд (React, @decky/ui, @decky/api):
  - `library.ts` — «Обновить библиотеку» (скан → `AddShortcut` → обложки → сопоставление) и фоновая очередь апскейла раз в 90 с (не во время игры)
  - `steam.ts` — `SteamClient.Apps.*`: добавление ярлыка (после `AddShortcut` обязательно `SetShortcutName/Exe/StartDir` — см. причуды ниже), `ClearCustomArtworkForApp` + `SetCustomArtworkForApp` (Steam пишет файл в grid и сразу показывает), позиция логотипа, `StoreItemCache`
  - `pagePatch.tsx` — замена содержимого родных вкладок (id `WhatsNew`, `YourStuff`, `Community`, `GameInfo`). `renderFunc` маршрута возвращает `<Provider value={pt}><AppPage overview details/></Provider>`; плагин подменяет `value` обёрткой над `pt`, та оборачивает компонент, который строит массив `tabs` (props `fnOnCancelFromTabHeader`+`details`), и меняет `children` вкладок. Обёртки кешируются в WeakMap (стабильный тип → без перемонтирования). **Не патчить через `createReactTreePatcher` глубже страницы:** страница — MobX observer-класс, после первой отрисовки `render` уходит в свойство экземпляра и патч прототипа откатывается.
  - `tabs.tsx`, `pageData.ts`, `modals.tsx`, `styles.tsx` (стили рендерятся `<style>` внутри компонента: страница игры живёт в окне Big Picture, а не в документе плагина)

- `achievementWatch.tsx` — уведомления о достижениях: `RegisterForAppLifetimeNotifications`, пока игра запущена — `poll_achievements` раз в 3 с (первый вызов — базовая точка, дальше только новые), ещё один опрос через 6 с после выхода (некоторые эмуляторы пишут файл при закрытии). Полученные достижения также показываются в Activity карточкой по дням.
- Если в Steam нет официальной картинки какого-то вида (некоторые старые игры: нет hero и логотипа), плагин ничего не придумывает (скриншоты, маленькие иконки — пользователь отказался от таких подстановок 2026-11-03): картинку ставят плагином SteamGridDB, а «Проверить обложки сейчас» подгоняет её размер.

## Команды
```bash
pnpm install && pnpm run typecheck && pnpm run build
python3 tests/test_backend.py
./scripts/deploy.sh user@host   # без sudo, через установщик Decky и CEF-отладчик Steam
```

## Проверено на ПК автора
- `SetCustomArtworkForApp(appid, b64, "jpg"|"png", type)` пишет `<appid>{p,,_hero,_logo}.<формат>` байт в байт; другой формат оставляет старый файл рядом → сначала `ClearCustomArtworkForApp` (он удаляет все варианты).
- Типы: portrait 0, hero 1, logo 2, wide 3. Позиция логотипа: `appDetailsStore.SaveCustomLogoPosition(overview, {...})`.
- `AddShortcut` сам берёт exe в кавычки, портит StartDir в кавычках и называет ярлык по exe.
- `StoreItemCache` и `partnerEventStore.LoadPartnerEventsPageable(undefined, appid, offset, n)` работают для некупленных игр.
- Апскейл upscayl-bin на RX 9060 XT: ~5 с на портрет/широкую (вместе с установкой в Steam). **Не передавать `-s`**: с ним upscayl-bin игнорирует `-r`/`-w` и сохраняет просто x4. Оригиналы перед заменой — в `settings/originals/`.
- Проверено на живом Steam: автодобавление игры из Anker (имя, кавычки, Proton, параметры запуска, картинки Steam), сопоставление всех ярлыков, вкладки и достижения работают, страницы Steam-игр не меняются.
- Скриншоты через CEF (`Page.captureScreenshot`) иногда приходят чёрными, хотя экран включён; тогда проверять по `document.body.innerText` окна Big Picture.

## Правила
- Плагин универсальный (для публикации): пути и привязки только через настройки.
- Из папок игр ничего не запускать, только читать.
- Не убивать процесс плагина вручную (Decky 3.3.1 зависает на 100% CPU до `sudo systemctl restart plugin_loader`).
