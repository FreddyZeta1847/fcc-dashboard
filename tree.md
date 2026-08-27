.
├── assets/
│   ├── logo.png
│   └── screenshot.png
├── backend/
│   ├── src/
│   │   └── fcc_dashboard/
│   │       ├── __init__.py
│   │       ├── __main__.py
│   │       ├── api.py
│   │       ├── collector.py
│   │       ├── datetime_utils.py
│   │       ├── db.py
│   │       ├── dependencies.py
│   │       ├── fcc_admin.py
│   │       ├── log_parser.py
│   │       ├── ports.py
│   │       ├── pricing.py
│   │       ├── process_control.py
│   │       ├── routes_control.py
│   │       ├── routes_db.py
│   │       ├── routes_fcc.py
│   │       ├── routes_pricing.py
│   │       ├── routes_requests.py
│   │       ├── routes_stats.py
│   │       ├── routes_status.py
│   │       └── static.py
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_api.py
│   │   ├── test_collector.py
│   │   ├── test_datetime_utils.py
│   │   ├── test_db.py
│   │   ├── test_fcc_admin.py
│   │   ├── test_log_parser.py
│   │   ├── test_placeholder.py
│   │   ├── test_ports.py
│   │   ├── test_pricing.py
│   │   ├── test_process_control.py
│   │   ├── test_routes_control.py
│   │   ├── test_routes_db.py
│   │   ├── test_routes_fcc.py
│   │   ├── test_routes_pricing.py
│   │   ├── test_routes_requests.py
│   │   ├── test_routes_stats.py
│   │   ├── test_routes_status.py
│   │   └── test_static.py
│   ├── .python-version
│   ├── pyproject.toml
│   ├── README.md
│   └── uv.lock
├── bin/
│   └── fcc-dashboard.js
├── dashboard request test/
├── docs/
│   └── superpowers/
│       └── plans/
│           ├── 2026-08-25-phase-0-scaffolding.md
│           ├── 2026-08-25-phase-1-core-utilities.md
│           ├── 2026-08-25-phase-2-persistence-collector.md
│           ├── 2026-08-25-phase-3-api.md
│           ├── 2026-08-25-phase-4-process-control.md
│           ├── 2026-08-25-phase-5-frontend-scaffold-overview.md
│           ├── 2026-08-25-phase-6a-settings-database.md
│           ├── 2026-08-25-phase-6b-usage-page.md
│           └── 2026-08-25-phase-7-integration-polish.md
├── frontend/
│   ├── public/
│   │   └── favicon.svg
│   ├── src/
│   │   ├── api/
│   │   │   ├── client.test.ts
│   │   │   ├── client.ts
│   │   │   └── types.ts
│   │   ├── assets/
│   │   ├── components/
│   │   │   ├── Card.tsx
│   │   │   ├── ConfirmDialog.tsx
│   │   │   ├── DailySavingsChart.test.tsx
│   │   │   ├── DailySavingsChart.tsx
│   │   │   ├── MoneySavedHeadline.test.tsx
│   │   │   ├── MoneySavedHeadline.tsx
│   │   │   ├── PriceRefreshFlow.test.tsx
│   │   │   ├── PriceRefreshFlow.tsx
│   │   │   ├── PricingEditor.fcc.test.tsx
│   │   │   ├── PricingEditor.test.tsx
│   │   │   ├── PricingEditor.tsx
│   │   │   ├── RangeSelector.test.tsx
│   │   │   ├── RangeSelector.tsx
│   │   │   ├── RecentRequestsFeed.test.tsx
│   │   │   ├── RecentRequestsFeed.tsx
│   │   │   ├── Sidebar.test.tsx
│   │   │   ├── Sidebar.tsx
│   │   │   ├── Skeleton.tsx
│   │   │   ├── StatusPanel.test.tsx
│   │   │   ├── StatusPanel.tsx
│   │   │   ├── Toast.tsx
│   │   │   ├── VolumeChart.test.tsx
│   │   │   └── VolumeChart.tsx
│   │   ├── hooks/
│   │   │   ├── useControl.ts
│   │   │   ├── useDbTables.ts
│   │   │   ├── useFccCatalog.ts
│   │   │   ├── usePricing.ts
│   │   │   ├── usePricingMutations.ts
│   │   │   ├── useRecentRequests.ts
│   │   │   ├── useStats.ts
│   │   │   ├── useStatus.ts
│   │   │   └── useTheme.ts
│   │   ├── lib/
│   │   │   └── processControlMessages.ts
│   │   ├── pages/
│   │   │   ├── Database.test.tsx
│   │   │   ├── Database.tsx
│   │   │   ├── Overview.test.tsx
│   │   │   ├── Overview.tsx
│   │   │   ├── Settings.test.tsx
│   │   │   ├── Settings.tsx
│   │   │   ├── Usage.test.tsx
│   │   │   └── Usage.tsx
│   │   ├── test/
│   │   │   ├── setup.test.ts
│   │   │   └── setup.ts
│   │   ├── App.test.tsx
│   │   ├── App.tsx
│   │   ├── index.css
│   │   └── main.tsx
│   ├── .gitignore
│   ├── .oxlintrc.json
│   ├── index.html
│   ├── package-lock.json
│   ├── package.json
│   ├── postcss.config.js
│   ├── tsconfig.app.json
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   └── vite.config.ts
├── .gitignore
├── .thumbnail
├── CHANGELOG.md
├── FCC Dashboard.dc.html
├── package.json
├── PROGRESS.md
├── README.md
├── support.js
└── tree.md
