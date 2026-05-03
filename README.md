You are Claude Code acting as a senior full-stack architect, backend engineer, frontend engineer, database engineer, and DevOps engineer.

Build a production-ready platform called:

UniFi ThreatFlow Hub

Purpose:
Create a central web platform that collects near-real-time network security and traffic-flow data from 50+ UniFi UDM Pro / UDM Pro Max firewalls across different branches.

The platform must focus on the same type of data visible in the UniFi Network application under the network/traffic/flows/security/threat/blocked views.

Important:
This is NOT an IPFIX collector.
This is NOT a generic SIEM.
This is NOT just syslog ingestion.
This must fetch data directly from each UniFi gateway/controller/firewall using the UniFi Network API/web API style endpoints where possible.

The platform must show:
- IDS/IPS events
- blocked traffic
- allowed traffic
- suspicious traffic
- top branches by suspicious traffic
- top visited domains
- top applications
- top traffic categories
- top risky clients
- top external destinations
- threat signatures
- policy actions
- branch health
- collector status
- long-term trend summaries

The system must be built properly for high log volume and must not slow down when storing large amounts of flow/threat data.

==================================================
HIGH-LEVEL ARCHITECTURE
==================================================

Use this architecture:

Frontend:
- Next.js
- React
- TypeScript
- TailwindCSS
- Dark NOC/SOC style dashboard
- Recharts or Apache ECharts
- Live auto-refresh every 30 seconds
- Global timeframe selector

Backend:
- FastAPI
- Python 3.12+
- Async workers
- httpx/aiohttp for collectors
- SQLAlchemy/Alembic for PostgreSQL
- ClickHouse native/http client for analytics storage
- Pydantic settings
- JWT/session-based authentication
- Role-based access control

Databases:
- PostgreSQL for control-plane data only:
  - users
  - roles
  - branches
  - credentials metadata
  - encrypted branch credentials
  - app settings
  - audit logs
  - collector configuration
  - dashboard preferences

- ClickHouse for all high-volume analytics data:
  - raw flow events
  - raw threat events
  - blocked events
  - IDS/IPS events
  - normalized traffic logs
  - rollups
  - dashboard analytics
  - branch scoring

Queue / cache:
- Redis or NATS
- Use for collector queueing, locking, backpressure, and dashboard cache

Deployment:
- Docker Compose
- Ubuntu 24.04 compatible
- Caddy or Traefik reverse proxy
- Environment-based configuration
- .env.example
- README.md
- Health checks
- Production-safe defaults

Do NOT store high-volume raw logs only in PostgreSQL.
Use PostgreSQL only for configuration/control-plane data.
Use ClickHouse for append-heavy analytics logs and fast dashboard queries.

==================================================
CORE FUNCTIONAL REQUIREMENTS
==================================================

The application must support 50+ UniFi branches/firewalls.

Each branch represents one UDM Pro, UDM Pro Max, or UniFi gateway/controller.

The system must fetch data from every enabled branch every 30 seconds.

Each branch must have:
- branch name
- branch code
- country
- city
- tags
- controller / UDM URL
- site ID
- gateway model
- authentication method
- username
- password
- API key/token when available
- SSL verification toggle
- polling interval
- enabled/disabled status
- notes
- created_at
- updated_at

The frontend must include an easy Branch Management page.

Branch Management page must include:
- list all branches
- add branch
- edit branch
- delete branch
- enable/disable polling
- test connection
- discover sites
- view collector status
- view last successful fetch
- view last error
- view UniFi OS version when available
- view Network app version when available
- view event count from last run
- view collector duration
- view endpoint used
- view branch health

The Add Branch page must include these buttons:
- Test Connection
- Discover Sites
- Save Branch
- Save & Start Collector

==================================================
DATA FETCHING / UNIFI COLLECTOR REQUIREMENTS
==================================================

Build a UniFi collector adapter system.

The collector must support different UniFi versions because endpoints may change.

Create adapter classes such as:
- BaseUniFiCollector
- UniFiNetworkV2TrafficFlowsCollector
- LegacyUniFiIpsEventCollector
- UniFiClientInventoryCollector
- UniFiDeviceInventoryCollector

The collector must attempt to use the newer traffic-flows endpoint first:

/proxy/network/v2/api/site/{site_id}/traffic-flows

Support fallback to older endpoint patterns such as:

/proxy/network/api/s/{site_id}/stat/ips/event

Also add support for fetching client/device metadata where available:

/proxy/network/api/s/{site_id}/stat/sta
/proxy/network/api/s/{site_id}/stat/device

Build the code so the endpoint paths are configurable per branch and per collector adapter.

Do not hardcode only one UniFi endpoint.
Create a flexible endpoint configuration model.

The collector must:
- authenticate to each UniFi branch
- maintain session/token when required
- fetch latest traffic flow/threat/blocked data
- fetch client inventory periodically
- normalize raw UniFi events into a common internal schema
- deduplicate events
- batch insert into ClickHouse
- update collector status in PostgreSQL
- log failures without crashing the entire collector service

The collector must run every 30 seconds per enabled branch.

Collector rules:
- max concurrent branch collectors configurable, default 10
- per-branch lock to prevent overlapping fetches
- timeout per branch, default 10 seconds
- retry count, default 2
- exponential backoff
- failed branch must not stop other branches
- all collector runs must be auditable
- collector must support dry-run/test mode
- collector must support mock data mode for frontend development

Deduplication:
Create stable event hashes based on:
- branch_id
- event_time
- source_ip
- source_port
- destination_ip
- destination_port
- protocol
- action
- policy_type
- policy_name
- signature
- risk/severity
- bytes/duration where useful

Never insert one event at a time.
Always use batch inserts into ClickHouse.

==================================================
TIME WINDOWS / DASHBOARD PERIODS
==================================================

The dashboard must support these timeframes globally:

- Past 5 minutes
- Past 15 minutes
- Past 1 hour
- Past 4 hours
- Past 12 hours
- Past 24 hours
- Past 3 days
- Past 7 days
- Past 14 days
- Past 1 month
- Past 6 months
- Past 1 year

Add a global timeframe selector at the top of every dashboard page:

[5m] [15m] [1h] [4h] [12h] [24h] [3d] [7d] [14d] [1m] [6m] [1y]

Every page must respect the selected timeframe.

Do not duplicate raw data into 12 separate full raw collections.
Instead:
- Store raw events once.
- Create efficient rollups/materialized views in ClickHouse.
- Use rollups for dashboard queries.

Recommended ClickHouse rollups:
- 1 minute rollup
- 5 minute rollup
- 15 minute rollup
- 1 hour rollup
- 1 day rollup

Dashboard timeframe mapping:
- 5m uses raw or 1m rollup
- 15m uses 1m rollup
- 1h uses 5m rollup
- 4h uses 15m rollup
- 12h uses 15m or 1h rollup
- 24h uses 1h rollup
- 3d uses 1h rollup
- 7d uses 1h or 1d rollup
- 14d uses 1d rollup
- 1m uses 1d rollup
- 6m uses 1d rollup
- 1y uses 1d rollup

==================================================
CLICKHOUSE DATABASE REQUIREMENTS
==================================================

Design ClickHouse properly for large log volumes.

Use MergeTree tables.

Partition raw event tables by date/month.

Use efficient ORDER BY keys.

Create the following ClickHouse tables:

1. raw_flow_events

Fields:
- event_id UUID
- event_hash String
- branch_id UUID
- branch_name LowCardinality(String)
- branch_code LowCardinality(String)
- event_time DateTime64
- ingest_time DateTime64
- action LowCardinality(String)
- risk LowCardinality(String)
- severity LowCardinality(String)
- policy_type LowCardinality(String)
- policy_name String
- source_ip IPv4/IPv6 or String fallback
- source_port UInt16
- source_mac String
- source_hostname String
- source_vlan String
- destination_ip IPv4/IPv6 or String fallback
- destination_port UInt16
- destination_hostname String
- destination_country LowCardinality(String)
- protocol LowCardinality(String)
- application String
- application_category LowCardinality(String)
- bytes_up UInt64
- bytes_down UInt64
- packets_up UInt64
- packets_down UInt64
- duration_ms UInt64
- direction LowCardinality(String)
- raw_json String or JSON type depending on ClickHouse support
- collector_version String

2. raw_threat_events

Fields:
- event_id UUID
- event_hash String
- branch_id UUID
- branch_name LowCardinality(String)
- branch_code LowCardinality(String)
- event_time DateTime64
- ingest_time DateTime64
- action LowCardinality(String)
- severity LowCardinality(String)
- risk LowCardinality(String)
- signature String
- threat_category LowCardinality(String)
- policy_type LowCardinality(String)
- policy_name String
- source_ip String
- source_port UInt16
- source_mac String
- source_hostname String
- destination_ip String
- destination_port UInt16
- destination_hostname String
- destination_country LowCardinality(String)
- protocol LowCardinality(String)
- client_ip String
- client_mac String
- client_hostname String
- raw_json String
- collector_version String

3. rollup_1m
4. rollup_5m
5. rollup_15m
6. rollup_1h
7. rollup_1d

Each rollup table must include:
- window_start
- window_end
- branch_id
- branch_name
- branch_code
- total_flows
- allowed_flows
- blocked_flows
- ids_ips_events
- high_risk_events
- medium_risk_events
- low_risk_events
- unique_clients
- unique_destinations
- total_bytes_up
- total_bytes_down
- top_clients JSON/String
- top_destinations JSON/String
- top_domains JSON/String
- top_apps JSON/String
- top_categories JSON/String
- top_signatures JSON/String
- top_countries JSON/String
- suspicion_score
- updated_at

Create materialized views or scheduled aggregation jobs to populate rollups.

Add TTL policies:
- raw_flow_events TTL configurable, default 90 days
- raw_threat_events TTL configurable, default 180 days
- 1m rollup TTL configurable, default 180 days
- 5m rollup TTL configurable, default 365 days
- 15m rollup TTL configurable, default 365 days
- 1h rollup TTL configurable, default 2 years
- 1d rollup TTL configurable, default 5 years

Add indexes/projections where useful for:
- event_time
- branch_id
- action
- severity/risk
- source_ip
- destination_ip
- destination_hostname
- application_category
- signature

ClickHouse insert requirements:
- batch inserts only
- async insert supported
- configurable batch size
- configurable flush interval
- backpressure handling
- insert failure retry handling
- dead-letter table or failed insert logging

==================================================
POSTGRESQL DATABASE REQUIREMENTS
==================================================

Use PostgreSQL for control-plane data.

Create tables:

users:
- id
- email
- name
- password_hash
- role
- enabled
- created_at
- updated_at

roles:
- id
- name
- permissions

branches:
- id
- name
- branch_code
- country
- city
- tags
- controller_url
- site_id
- gateway_model
- auth_method
- ssl_verify
- polling_interval_seconds
- enabled
- notes
- created_at
- updated_at

branch_credentials:
- id
- branch_id
- encrypted_username
- encrypted_password
- encrypted_api_key
- encrypted_token
- created_at
- updated_at

collector_status:
- branch_id
- status
- last_success_at
- last_error_at
- last_error
- last_duration_ms
- last_event_count
- last_endpoint_used
- unifi_os_version
- network_app_version
- collector_version
- updated_at

collector_runs:
- id
- branch_id
- started_at
- finished_at
- status
- event_count
- error_message
- endpoint_used
- duration_ms

app_settings:
- key
- value
- updated_at

audit_logs:
- id
- user_id
- action
- entity_type
- entity_id
- metadata_json
- created_at

Use Alembic migrations.

Encrypt all branch credentials at rest using Fernet or an equivalent secure encryption method.

Never expose branch credentials to the frontend.

==================================================
SUSPICION SCORE
==================================================

Create a suspicion scoring engine.

Default scoring:
- High-risk IDS/IPS event: +10
- Medium-risk IDS/IPS event: +5
- Low-risk event: +1
- Blocked intrusion event: +4
- Repeated same-client detection: +8
- Outbound suspicious destination: +6
- Malware/botnet signature: +15
- Large unusual data transfer: +5
- Known false positive: -3

Make scoring weights configurable from the Settings page.

The dashboard must show:
- Top suspicious branches
- Top suspicious clients
- Top suspicious destinations
- Top signatures
- Suspicion score trend over time

==================================================
FRONTEND REQUIREMENTS
==================================================

Build a dark SOC/NOC-style dashboard.

Sidebar menu:

- Overview
- Threats
- Blocked Traffic
- Top Visited
- Branches
- Clients
- Destinations
- Categories
- Suspicion Score
- Collector Health
- Storage Health
- Settings

Overview page:
- total branches
- online/offline collectors
- total flows in selected timeframe
- blocked flows
- allowed flows
- IDS/IPS events
- high-risk events
- top suspicious branch
- top suspicious client
- traffic volume trend
- threat trend
- branch risk heatmap/table

Threats page:
- filterable table
- branch filter
- severity filter
- signature filter
- source/destination filter
- action filter
- timeframe filter
- export CSV
- drilldown into raw event

Blocked Traffic page:
- blocked sessions
- blocked by branch
- blocked by client
- blocked by destination
- blocked by policy
- blocked by country
- blocked trend

Top Visited page:
- top domains
- top applications
- top categories
- top clients
- top branches by traffic
- top external destinations
- bytes up/down
- sessions

Branches page:
- branch list
- add branch
- edit branch
- delete branch
- enable/disable branch
- test connection
- discover sites
- health status
- last fetch details

Branch detail page:
- branch metadata
- live status
- suspicious score
- latest threats
- top clients
- top destinations
- top categories
- top signatures
- traffic trend
- collector health

Clients page:
- search clients
- top clients by traffic
- top clients by threat count
- top clients by blocked flows
- client detail page

Client detail page:
- all recent flows
- all threat events
- all blocked events
- destination history
- application/category history
- risk trend

Destinations page:
- top destination IPs
- top domains
- top countries
- risky destinations
- destination detail page

Categories page:
- application categories
- threat categories
- content categories where available

Suspicion Score page:
- branch ranking
- client ranking
- destination ranking
- configurable scoring explanation
- trend charts

Collector Health page:
- all collectors
- last success
- last error
- status
- duration
- events fetched
- endpoint used
- UniFi version info
- manual run/test collector action

Storage Health page:
- ClickHouse row counts
- events per day
- GB per day
- disk usage
- compression ratio if available
- oldest raw event
- retention settings
- failed insert count
- rollup freshness

Settings page:
- retention settings
- collector concurrency
- polling interval defaults
- scoring weights
- user management
- role management
- API keys
- backup settings

All dashboard pages must:
- respect global timeframe selector
- auto-refresh every 30 seconds
- use loading states
- use error states
- avoid blocking UI
- use paginated queries for raw tables

==================================================
API REQUIREMENTS
==================================================

Create FastAPI endpoints:

Auth:
- POST /api/auth/login
- POST /api/auth/logout
- GET /api/auth/me

Branches:
- GET /api/branches
- POST /api/branches
- GET /api/branches/{id}
- PUT /api/branches/{id}
- DELETE /api/branches/{id}
- POST /api/branches/{id}/test-connection
- POST /api/branches/{id}/discover-sites
- POST /api/branches/{id}/enable
- POST /api/branches/{id}/disable

Dashboard:
- GET /api/dashboard/overview?timeframe=
- GET /api/dashboard/top-suspicious-branches?timeframe=
- GET /api/dashboard/threat-trend?timeframe=
- GET /api/dashboard/traffic-trend?timeframe=

Threats:
- GET /api/threats?timeframe=&branch_id=&severity=&signature=&page=
- GET /api/threats/{event_id}

Blocked:
- GET /api/blocked?timeframe=&branch_id=&page=
- GET /api/blocked/top-destinations?timeframe=
- GET /api/blocked/top-clients?timeframe=

Top Visited:
- GET /api/top/domains?timeframe=
- GET /api/top/applications?timeframe=
- GET /api/top/categories?timeframe=
- GET /api/top/clients?timeframe=
- GET /api/top/destinations?timeframe=

Clients:
- GET /api/clients?timeframe=&search=
- GET /api/clients/{client_id}
- GET /api/clients/{client_id}/flows
- GET /api/clients/{client_id}/threats

Collector:
- GET /api/collectors/status
- POST /api/collectors/run-all
- POST /api/collectors/run-branch/{branch_id}

Storage:
- GET /api/storage/health
- GET /api/storage/retention
- PUT /api/storage/retention

Settings:
- GET /api/settings
- PUT /api/settings
- GET /api/scoring
- PUT /api/scoring

==================================================
SECURITY REQUIREMENTS
==================================================

Security is important.

Implement:
- login system
- password hashing
- role-based access control
- session/JWT security
- encrypted branch credentials
- audit logging
- rate limiting for login and API
- backend-only credential usage
- no credentials in frontend
- secure .env handling
- CORS configuration
- HTTP security headers through reverse proxy
- read-only branch credentials recommended
- SSL verify toggle per branch, but warn when disabled
- no debug mode in production

==================================================
DEVOPS / DEPLOYMENT REQUIREMENTS
==================================================

Create Docker Compose stack with:

- frontend
- backend
- collector
- postgres
- clickhouse
- redis or nats
- reverse proxy
- optional backup service

Create:
- docker-compose.yml
- docker-compose.override.yml for development
- .env.example
- README.md
- scripts/init.sh
- scripts/backup.sh
- scripts/restore.sh
- scripts/create-admin.sh
- scripts/run-migrations.sh
- scripts/healthcheck.sh

The README must include:
- requirements
- installation
- first login
- adding first branch
- testing UniFi connection
- enabling collectors
- viewing dashboard
- backup/restore
- production notes
- sizing recommendations
- troubleshooting

Use health checks for all containers.

Make sure the platform can run on Ubuntu 24.04.

==================================================
SERVER SIZING NOTES
==================================================

Include these recommendations in the README:

Minimum production single-server:
- 24 cores
- 128 GB RAM
- 15 TB usable enterprise NVMe
- 1 Gbps network minimum
- 10 Gbps preferred

Recommended production split:
App/collector server:
- 12–16 cores
- 64 GB RAM
- 1 TB NVMe

Database server:
- 32 cores
- 256 GB ECC RAM
- 30 TB usable enterprise NVMe
- 10 Gbps network

Use enterprise NVMe SSDs with power-loss protection.
Avoid HDDs for live ClickHouse storage.

==================================================
MOCK DATA MODE
==================================================

Implement mock data mode.

Mock data mode must:
- generate fake branches
- generate fake flows
- generate fake threats
- generate blocked events
- generate top domains/apps/categories
- generate collector status
- allow frontend development without real UniFi devices

Add .env setting:

MOCK_DATA=true

When enabled:
- collectors use mock generators
- dashboard still uses same APIs
- database still receives realistic mock events

==================================================
TESTING REQUIREMENTS
==================================================

Create tests for:

Backend:
- auth
- branch CRUD
- credential encryption
- collector status updates
- timeframe parsing
- suspicion scoring
- ClickHouse query builder
- API filters

Collector:
- adapter selection
- event normalization
- deduplication hash
- batch insert formatting
- retry/backoff behavior
- per-branch lock

Frontend:
- render main pages
- timeframe selector
- branch form validation
- table filters
- loading/error states

Add seed data and mock fixtures.

==================================================
PERFORMANCE REQUIREMENTS
==================================================

The system must handle:
- 50 branches
- fetch every 30 seconds
- thousands of events per second during bursts
- fast dashboard queries
- long-term rollups up to 1 year
- no full raw scans for dashboard overview pages

Important performance rules:
- never query raw tables for 6m or 1y dashboards
- use ClickHouse rollups
- use pagination
- use time filters in every analytics query
- use batch inserts
- use connection pooling
- use async workers
- cache common dashboard responses briefly
- prevent collector overlap per branch
- add backpressure if ClickHouse is slow

==================================================
DEVELOPMENT EXECUTION PLAN
==================================================

Build this project in phases, but generate complete working code for each phase.

Phase 1:
- create monorepo structure
- Docker Compose
- PostgreSQL
- ClickHouse
- Redis/NATS
- FastAPI backend
- Next.js frontend
- basic auth
- dark layout

Phase 2:
- PostgreSQL migrations
- branch management
- credential encryption
- branch CRUD API
- branch UI
- test connection stub

Phase 3:
- ClickHouse schema
- raw event tables
- rollup tables
- materialized views or aggregation jobs
- storage health API

Phase 4:
- collector service
- UniFi adapter interface
- traffic-flows collector
- legacy IPS fallback collector
- mock data collector
- scheduler every 30 seconds
- dedupe and batch insert

Phase 5:
- dashboard APIs
- overview page
- threats page
- blocked page
- top visited page
- branch detail page
- collector health page

Phase 6:
- suspicion scoring
- scoring settings
- top suspicious branches/clients/destinations
- trend charts

Phase 7:
- tests
- documentation
- production hardening
- backup/restore scripts

At each phase:
- write real code
- do not leave TODO-only files
- do not create fake placeholders where real logic is possible
- keep code clean and modular
- document any UniFi endpoint assumptions clearly
- make endpoint paths configurable
- include error handling

==================================================
PROJECT STRUCTURE
==================================================

Use this structure:

unifi-threatflow-hub/
  backend/
    app/
      main.py
      config.py
      auth/
      api/
      models/
      schemas/
      services/
      db/
      clickhouse/
      collectors/
      scoring/
      utils/
    alembic/
    tests/
    Dockerfile
    requirements.txt

  frontend/
    app/
    components/
    lib/
    pages or app router/
    styles/
    Dockerfile
    package.json
    tsconfig.json

  collector/
    app/
      main.py
      scheduler.py
      workers.py
      adapters/
      normalizers/
      mock/
      dedupe.py
      batch_writer.py
    Dockerfile

  infra/
    clickhouse/
      init/
      config/
    postgres/
    caddy/
    redis/

  scripts/
    init.sh
    backup.sh
    restore.sh
    create-admin.sh
    run-migrations.sh
    healthcheck.sh

  docker-compose.yml
  docker-compose.override.yml
  .env.example
  README.md

==================================================
IMPORTANT UNIFI ENDPOINT NOTE
==================================================

UniFi endpoints can change between Network versions.

Therefore:
- create a flexible adapter system
- allow endpoint paths to be configured
- log which endpoint worked
- store endpoint_used in collector_status
- build a "Test Connection" and "Discover Sites" flow
- allow future endpoint adapters to be added easily
- include instructions in README explaining how to capture the exact traffic-flows request from browser DevTools if needed

The first implementation should support:

Preferred:
POST or GET depending on discovered behavior:
/proxy/network/v2/api/site/{site_id}/traffic-flows

Fallback:
/proxy/network/api/s/{site_id}/stat/ips/event

Client/device enrichment:
/proxy/network/api/s/{site_id}/stat/sta
/proxy/network/api/s/{site_id}/stat/device

Make request method, payload and filters configurable.

==================================================
FINAL DELIVERABLE
==================================================

Deliver a complete working project.

The final result must include:
- full source code
- Docker Compose stack
- PostgreSQL migrations
- ClickHouse schema
- backend API
- collector service
- frontend dashboard
- branch management UI
- mock data mode
- README
- backup/restore scripts
- tests

Prioritize:
1. correct scalable architecture
2. fast database design
3. reliable collectors
4. clean dashboard UX
5. production safety
6. easy branch onboarding

Start by generating the complete project structure and implementation.
