import { branchesApi } from "./branches";
import { topApi } from "./dashboard";
import type { FilterDef } from "@/components/AdvancedFilters";
import type { Timeframe } from "./timeframe";

const SEVERITIES = [
  { value: "informational", label: "informational" },
  { value: "warning", label: "warning" },
  { value: "critical", label: "critical" },
  { value: "low", label: "low" },
  { value: "medium", label: "medium" },
  { value: "high", label: "high" },
];
const ACTIONS = [
  { value: "allow", label: "allow" },
  { value: "block", label: "block" },
];
const RISKS = [
  { value: "low", label: "low" },
  { value: "medium", label: "medium" },
  { value: "high", label: "high" },
];
const POLICY_TYPES = [
  { value: "allow",     label: "allow" },
  { value: "firewall",  label: "firewall" },
  { value: "ids",       label: "ids" },
  { value: "ips",       label: "ips" },
  { value: "ids_ips",   label: "ids_ips" },
];
const COLLECTOR_STATES = [
  { value: "ok",        label: "ok" },
  { value: "error",     label: "error" },
  { value: "running",   label: "running" },
  { value: "never_run", label: "never run" },
];

const branchOptions = async () => {
  try {
    const r = await branchesApi.list();
    return r.items.map((b) => ({ value: b.id, label: `${b.branch_code} — ${b.name}` }));
  } catch { return []; }
};
const countryOptions = (tf: Timeframe = "24h") => async () => {
  try {
    const r = await topApi.countries(tf, 50);
    return r.items.map((i) => ({ value: i.label, label: i.label }));
  } catch { return []; }
};
const categoryOptions = (tf: Timeframe = "24h") => async () => {
  try {
    const r = await topApi.categories(tf, 50);
    return r.items.map((i) => ({ value: i.label, label: i.label }));
  } catch { return []; }
};

export const THREAT_FILTERS: FilterDef[] = [
  { key: "branch_id",       label: "Branch",      type: "select", loadOptions: branchOptions },
  { key: "severity",        label: "Severity",    type: "select", options: SEVERITIES },
  { key: "risk",            label: "Risk",        type: "select", options: RISKS },
  { key: "action",          label: "Action",      type: "select", options: ACTIONS },
  { key: "signature",       label: "Signature",   type: "contains", placeholder: "Cobalt, Trojan, …" },
  { key: "source_ip",       label: "Source IP",   type: "text",   placeholder: "10.0.0.5" },
  { key: "destination_ip",  label: "Dest IP",     type: "text",   placeholder: "1.1.1.1" },
  { key: "destination_hostname", label: "Hostname", type: "contains", placeholder: "youtube" },
  { key: "country",         label: "Country",     type: "select", loadOptions: countryOptions() },
  { key: "threat_category", label: "Threat cat",  type: "contains" },
];

export const BLOCKED_FILTERS: FilterDef[] = [
  { key: "branch_id",       label: "Branch",      type: "select", loadOptions: branchOptions },
  { key: "risk",            label: "Risk",        type: "select", options: RISKS },
  { key: "source_ip",       label: "Source IP",   type: "text" },
  { key: "destination_ip",  label: "Dest IP",     type: "text" },
  { key: "destination_hostname", label: "Hostname", type: "contains" },
  { key: "country",         label: "Country",     type: "select", loadOptions: countryOptions() },
  { key: "application",     label: "Application", type: "text",   placeholder: "Spotify" },
  { key: "application_category", label: "Category", type: "select", loadOptions: categoryOptions() },
  { key: "policy_name",     label: "Policy",      type: "contains" },
];

export const CLIENT_FILTERS: FilterDef[] = [
  { key: "branch_id",       label: "Branch",      type: "select", loadOptions: branchOptions },
  { key: "search",          label: "Search",      type: "contains", placeholder: "ip / hostname" },
  { key: "min_threats",     label: "Min threats", type: "number-min" },
  { key: "min_blocked",     label: "Min blocked", type: "number-min" },
];

export const BRANCH_FILTERS: FilterDef[] = [
  { key: "search",          label: "Name / code", type: "contains" },
  { key: "country",         label: "Country",     type: "text" },
  { key: "tag",             label: "Tag",         type: "text",   placeholder: "apac" },
  { key: "enabled",         label: "Enabled",     type: "boolean" },
  { key: "online",          label: "Online only", type: "boolean" },
  { key: "status",          label: "Status",      type: "select", options: COLLECTOR_STATES },
];
