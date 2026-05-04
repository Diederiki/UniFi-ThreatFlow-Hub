-- =============================================================================
-- UniFi ThreatFlow Hub — ClickHouse schema (Phase 3)
-- Idempotent (CREATE … IF NOT EXISTS) so it can be re-applied safely from
-- backend/app/cli/migrate_clickhouse.py without dropping data.
-- =============================================================================

CREATE DATABASE IF NOT EXISTS threatflow;

-- -----------------------------------------------------------------------------
-- Raw event tables (ReplacingMergeTree on event_hash for natural dedup)
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS threatflow.raw_flow_events (
    event_id              UUID DEFAULT generateUUIDv4(),
    event_hash            String CODEC(ZSTD(1)),
    branch_id             UUID,
    branch_name           LowCardinality(String),
    branch_code           LowCardinality(String),
    event_time            DateTime64(3, 'UTC'),
    ingest_time           DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC'),
    action                LowCardinality(String),
    risk                  LowCardinality(String),
    severity              LowCardinality(String),
    policy_type           LowCardinality(String),
    policy_name           String,
    source_ip             String,
    source_port           UInt16,
    source_mac            String,
    source_hostname       String,
    source_vlan           String,
    destination_ip        String,
    destination_port      UInt16,
    destination_hostname  String,
    destination_country   LowCardinality(String),
    protocol              LowCardinality(String),
    application           String,
    application_category  LowCardinality(String),
    bytes_up              UInt64,
    bytes_down            UInt64,
    packets_up            UInt64,
    packets_down          UInt64,
    duration_ms           UInt64,
    direction             LowCardinality(String),
    raw_json              String CODEC(ZSTD(3)),
    collector_version     LowCardinality(String),
    INDEX idx_dest_ip       destination_ip       TYPE bloom_filter GRANULARITY 4,
    INDEX idx_dest_host     destination_hostname TYPE bloom_filter GRANULARITY 4,
    INDEX idx_app_category  application_category TYPE set(0)         GRANULARITY 4
) ENGINE = ReplacingMergeTree(ingest_time)
PARTITION BY toYYYYMM(event_time)
ORDER BY (branch_id, event_time, event_hash)
TTL toDateTime(event_time) + INTERVAL 90 DAY DELETE
SETTINGS index_granularity = 8192;


CREATE TABLE IF NOT EXISTS threatflow.raw_threat_events (
    event_id              UUID DEFAULT generateUUIDv4(),
    event_hash            String CODEC(ZSTD(1)),
    branch_id             UUID,
    branch_name           LowCardinality(String),
    branch_code           LowCardinality(String),
    event_time            DateTime64(3, 'UTC'),
    ingest_time           DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC'),
    action                LowCardinality(String),
    severity              LowCardinality(String),
    risk                  LowCardinality(String),
    signature             String,
    threat_category       LowCardinality(String),
    policy_type           LowCardinality(String),
    policy_name           String,
    source_ip             String,
    source_port           UInt16,
    source_mac            String,
    source_hostname       String,
    destination_ip        String,
    destination_port      UInt16,
    destination_hostname  String,
    destination_country   LowCardinality(String),
    protocol              LowCardinality(String),
    client_ip             String,
    client_mac            String,
    client_hostname       String,
    mitre_techniques      Array(LowCardinality(String)) DEFAULT [],
    mitre_tactics         Array(LowCardinality(String)) DEFAULT [],
    cve_refs              Array(String) DEFAULT [],
    raw_json              String CODEC(ZSTD(3)),
    collector_version     LowCardinality(String),
    INDEX idx_signature       signature        TYPE bloom_filter GRANULARITY 4,
    INDEX idx_threat_category threat_category  TYPE set(0)        GRANULARITY 4,
    INDEX idx_mitre_tech      mitre_techniques TYPE bloom_filter GRANULARITY 4,
    INDEX idx_cve_refs        cve_refs         TYPE bloom_filter GRANULARITY 4
) ENGINE = ReplacingMergeTree(ingest_time)
PARTITION BY toYYYYMM(event_time)
ORDER BY (branch_id, event_time, event_hash)
TTL toDateTime(event_time) + INTERVAL 180 DAY DELETE
SETTINGS index_granularity = 8192;

-- For databases created before the MITRE/CVE columns were added, idempotently
-- bring them up to schema. ClickHouse 24+ supports IF NOT EXISTS on columns + indexes.
ALTER TABLE threatflow.raw_threat_events ADD COLUMN IF NOT EXISTS mitre_techniques Array(LowCardinality(String)) DEFAULT [] AFTER client_hostname;
ALTER TABLE threatflow.raw_threat_events ADD COLUMN IF NOT EXISTS mitre_tactics    Array(LowCardinality(String)) DEFAULT [] AFTER mitre_techniques;
ALTER TABLE threatflow.raw_threat_events ADD COLUMN IF NOT EXISTS cve_refs         Array(String)                  DEFAULT [] AFTER mitre_tactics;
ALTER TABLE threatflow.raw_threat_events ADD INDEX IF NOT EXISTS idx_mitre_tech mitre_techniques TYPE bloom_filter GRANULARITY 4;
ALTER TABLE threatflow.raw_threat_events ADD INDEX IF NOT EXISTS idx_cve_refs   cve_refs         TYPE bloom_filter GRANULARITY 4;


CREATE TABLE IF NOT EXISTS threatflow.failed_inserts (
    failed_at  DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC'),
    target     LowCardinality(String),
    branch_id  UUID,
    rows       UInt32,
    error      String,
    payload_sample String
) ENGINE = MergeTree
PARTITION BY toYYYYMM(failed_at)
ORDER BY (failed_at, target)
TTL toDateTime(failed_at) + INTERVAL 30 DAY DELETE;


-- -----------------------------------------------------------------------------
-- Rollups — AggregatingMergeTree so we can store both summable counters AND
-- mergeable uniq / topK state. Each MV writes directly from raw_flow_events
-- (we deliberately do NOT chain MVs so every rollup is independently rebuildable).
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS threatflow.rollup_1m (
    window_start          DateTime,
    branch_id             UUID,
    branch_name           LowCardinality(String),
    branch_code           LowCardinality(String),
    total_flows           AggregateFunction(sum, UInt64),
    allowed_flows         AggregateFunction(sum, UInt64),
    blocked_flows         AggregateFunction(sum, UInt64),
    ids_ips_events        AggregateFunction(sum, UInt64),
    high_risk_events      AggregateFunction(sum, UInt64),
    medium_risk_events    AggregateFunction(sum, UInt64),
    low_risk_events       AggregateFunction(sum, UInt64),
    total_bytes_up        AggregateFunction(sum, UInt64),
    total_bytes_down      AggregateFunction(sum, UInt64),
    unique_clients        AggregateFunction(uniq, String),
    unique_destinations   AggregateFunction(uniq, String),
    top_clients           AggregateFunction(topK(20), String),
    top_destinations      AggregateFunction(topK(20), String),
    top_domains           AggregateFunction(topK(20), String),
    top_apps              AggregateFunction(topK(20), String),
    top_categories        AggregateFunction(topK(20), String),
    top_countries         AggregateFunction(topK(20), String)
) ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMM(window_start)
ORDER BY (window_start, branch_id)
TTL window_start + INTERVAL 180 DAY DELETE;


CREATE TABLE IF NOT EXISTS threatflow.rollup_5m   AS threatflow.rollup_1m ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMM(window_start) ORDER BY (window_start, branch_id) TTL window_start + INTERVAL 365 DAY DELETE;

CREATE TABLE IF NOT EXISTS threatflow.rollup_15m  AS threatflow.rollup_1m ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMM(window_start) ORDER BY (window_start, branch_id) TTL window_start + INTERVAL 365 DAY DELETE;

CREATE TABLE IF NOT EXISTS threatflow.rollup_1h   AS threatflow.rollup_1m ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMM(window_start) ORDER BY (window_start, branch_id) TTL window_start + INTERVAL 730 DAY DELETE;

CREATE TABLE IF NOT EXISTS threatflow.rollup_1d   AS threatflow.rollup_1m ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMM(window_start) ORDER BY (window_start, branch_id) TTL window_start + INTERVAL 1825 DAY DELETE;


-- -----------------------------------------------------------------------------
-- Materialized views — one per resolution. Same SELECT shape, different
-- toStartOf… function so the time bucket changes.
-- -----------------------------------------------------------------------------

CREATE MATERIALIZED VIEW IF NOT EXISTS threatflow.mv_rollup_1m TO threatflow.rollup_1m AS
SELECT
    toStartOfMinute(event_time)                                                 AS window_start,
    branch_id, branch_name, branch_code,
    sumState(toUInt64(1))                                                       AS total_flows,
    sumState(toUInt64(action = 'allow'))                                        AS allowed_flows,
    sumState(toUInt64(action = 'block'))                                        AS blocked_flows,
    sumState(toUInt64(policy_type IN ('ids', 'ips', 'ids_ips')))                AS ids_ips_events,
    sumState(toUInt64(risk = 'high'))                                           AS high_risk_events,
    sumState(toUInt64(risk = 'medium'))                                         AS medium_risk_events,
    sumState(toUInt64(risk = 'low'))                                            AS low_risk_events,
    sumState(toUInt64(bytes_up))                                                AS total_bytes_up,
    sumState(toUInt64(bytes_down))                                              AS total_bytes_down,
    uniqState(source_ip)                                                        AS unique_clients,
    uniqState(destination_ip)                                                   AS unique_destinations,
    topKState(20)(source_ip)                                                    AS top_clients,
    topKState(20)(destination_ip)                                               AS top_destinations,
    topKState(20)(destination_hostname)                                         AS top_domains,
    topKState(20)(application)                                                  AS top_apps,
    topKState(20)(application_category)                                         AS top_categories,
    topKState(20)(destination_country)                                          AS top_countries
FROM threatflow.raw_flow_events
GROUP BY window_start, branch_id, branch_name, branch_code;


CREATE MATERIALIZED VIEW IF NOT EXISTS threatflow.mv_rollup_5m TO threatflow.rollup_5m AS
SELECT
    toStartOfFiveMinute(event_time)                                             AS window_start,
    branch_id, branch_name, branch_code,
    sumState(toUInt64(1))                                                       AS total_flows,
    sumState(toUInt64(action = 'allow'))                                        AS allowed_flows,
    sumState(toUInt64(action = 'block'))                                        AS blocked_flows,
    sumState(toUInt64(policy_type IN ('ids', 'ips', 'ids_ips')))                AS ids_ips_events,
    sumState(toUInt64(risk = 'high'))                                           AS high_risk_events,
    sumState(toUInt64(risk = 'medium'))                                         AS medium_risk_events,
    sumState(toUInt64(risk = 'low'))                                            AS low_risk_events,
    sumState(toUInt64(bytes_up))                                                AS total_bytes_up,
    sumState(toUInt64(bytes_down))                                              AS total_bytes_down,
    uniqState(source_ip)                                                        AS unique_clients,
    uniqState(destination_ip)                                                   AS unique_destinations,
    topKState(20)(source_ip)                                                    AS top_clients,
    topKState(20)(destination_ip)                                               AS top_destinations,
    topKState(20)(destination_hostname)                                         AS top_domains,
    topKState(20)(application)                                                  AS top_apps,
    topKState(20)(application_category)                                         AS top_categories,
    topKState(20)(destination_country)                                          AS top_countries
FROM threatflow.raw_flow_events
GROUP BY window_start, branch_id, branch_name, branch_code;


CREATE MATERIALIZED VIEW IF NOT EXISTS threatflow.mv_rollup_15m TO threatflow.rollup_15m AS
SELECT
    toStartOfInterval(event_time, INTERVAL 15 MINUTE)                           AS window_start,
    branch_id, branch_name, branch_code,
    sumState(toUInt64(1))                                                       AS total_flows,
    sumState(toUInt64(action = 'allow'))                                        AS allowed_flows,
    sumState(toUInt64(action = 'block'))                                        AS blocked_flows,
    sumState(toUInt64(policy_type IN ('ids', 'ips', 'ids_ips')))                AS ids_ips_events,
    sumState(toUInt64(risk = 'high'))                                           AS high_risk_events,
    sumState(toUInt64(risk = 'medium'))                                         AS medium_risk_events,
    sumState(toUInt64(risk = 'low'))                                            AS low_risk_events,
    sumState(toUInt64(bytes_up))                                                AS total_bytes_up,
    sumState(toUInt64(bytes_down))                                              AS total_bytes_down,
    uniqState(source_ip)                                                        AS unique_clients,
    uniqState(destination_ip)                                                   AS unique_destinations,
    topKState(20)(source_ip)                                                    AS top_clients,
    topKState(20)(destination_ip)                                               AS top_destinations,
    topKState(20)(destination_hostname)                                         AS top_domains,
    topKState(20)(application)                                                  AS top_apps,
    topKState(20)(application_category)                                         AS top_categories,
    topKState(20)(destination_country)                                          AS top_countries
FROM threatflow.raw_flow_events
GROUP BY window_start, branch_id, branch_name, branch_code;


CREATE MATERIALIZED VIEW IF NOT EXISTS threatflow.mv_rollup_1h TO threatflow.rollup_1h AS
SELECT
    toStartOfHour(event_time)                                                   AS window_start,
    branch_id, branch_name, branch_code,
    sumState(toUInt64(1))                                                       AS total_flows,
    sumState(toUInt64(action = 'allow'))                                        AS allowed_flows,
    sumState(toUInt64(action = 'block'))                                        AS blocked_flows,
    sumState(toUInt64(policy_type IN ('ids', 'ips', 'ids_ips')))                AS ids_ips_events,
    sumState(toUInt64(risk = 'high'))                                           AS high_risk_events,
    sumState(toUInt64(risk = 'medium'))                                         AS medium_risk_events,
    sumState(toUInt64(risk = 'low'))                                            AS low_risk_events,
    sumState(toUInt64(bytes_up))                                                AS total_bytes_up,
    sumState(toUInt64(bytes_down))                                              AS total_bytes_down,
    uniqState(source_ip)                                                        AS unique_clients,
    uniqState(destination_ip)                                                   AS unique_destinations,
    topKState(20)(source_ip)                                                    AS top_clients,
    topKState(20)(destination_ip)                                               AS top_destinations,
    topKState(20)(destination_hostname)                                         AS top_domains,
    topKState(20)(application)                                                  AS top_apps,
    topKState(20)(application_category)                                         AS top_categories,
    topKState(20)(destination_country)                                          AS top_countries
FROM threatflow.raw_flow_events
GROUP BY window_start, branch_id, branch_name, branch_code;


CREATE MATERIALIZED VIEW IF NOT EXISTS threatflow.mv_rollup_1d TO threatflow.rollup_1d AS
SELECT
    toStartOfDay(event_time)                                                    AS window_start,
    branch_id, branch_name, branch_code,
    sumState(toUInt64(1))                                                       AS total_flows,
    sumState(toUInt64(action = 'allow'))                                        AS allowed_flows,
    sumState(toUInt64(action = 'block'))                                        AS blocked_flows,
    sumState(toUInt64(policy_type IN ('ids', 'ips', 'ids_ips')))                AS ids_ips_events,
    sumState(toUInt64(risk = 'high'))                                           AS high_risk_events,
    sumState(toUInt64(risk = 'medium'))                                         AS medium_risk_events,
    sumState(toUInt64(risk = 'low'))                                            AS low_risk_events,
    sumState(toUInt64(bytes_up))                                                AS total_bytes_up,
    sumState(toUInt64(bytes_down))                                              AS total_bytes_down,
    uniqState(source_ip)                                                        AS unique_clients,
    uniqState(destination_ip)                                                   AS unique_destinations,
    topKState(20)(source_ip)                                                    AS top_clients,
    topKState(20)(destination_ip)                                               AS top_destinations,
    topKState(20)(destination_hostname)                                         AS top_domains,
    topKState(20)(application)                                                  AS top_apps,
    topKState(20)(application_category)                                         AS top_categories,
    topKState(20)(destination_country)                                          AS top_countries
FROM threatflow.raw_flow_events
GROUP BY window_start, branch_id, branch_name, branch_code;
