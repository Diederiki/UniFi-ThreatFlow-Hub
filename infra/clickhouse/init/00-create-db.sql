-- Phase 1: bare-minimum bootstrap. Phase 3 will replace this with full schema
-- (raw_flow_events, raw_threat_events, rollup_1m / 5m / 15m / 1h / 1d, MVs, TTLs).
CREATE DATABASE IF NOT EXISTS threatflow;
