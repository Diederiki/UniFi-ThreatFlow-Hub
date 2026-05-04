-- Optional Postgres table that maps a branch's WAN-side public IP to
-- its threatflow `branches.id`. Populated manually (or from /ea/sites
-- ispInfo data) so the IPFIX collector can attribute incoming flows.
--
-- If this table doesn't exist the collector falls back to synthesising
-- an "unknown:<ip>" branch_code so the rows still land — handy for
-- bootstrap before you've mapped every gateway.

CREATE TABLE IF NOT EXISTS branch_wan_ips (
    wan_ip      INET PRIMARY KEY,
    branch_id   UUID NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    notes       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_branch_wan_ips_branch_id ON branch_wan_ips (branch_id);
