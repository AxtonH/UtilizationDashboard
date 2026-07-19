"""Business logic for retrieving creative employees from Odoo."""
from __future__ import annotations

import copy
import threading
import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple
import xmlrpc.client

from ..config import Config, OdooSettings
from ..integrations.odoo_client import OdooClient


# The field-existence probes and fields_get relations depend only on the Odoo
# schema (which Studio fields exist), never on request data, so they are shared
# process-wide. The TTL lets newly added/removed Studio fields be picked up
# without a restart.
_FIELD_SCHEMA_CACHE: Dict[Tuple[str, str], Dict[str, Any]] = {}
_FIELD_SCHEMA_CACHE_LOCK = threading.Lock()
_FIELD_SCHEMA_TTL_SECONDS = 600.0

# Short-lived memo of fetched employee lists. A single dashboard request fetches
# the same employees several times across services and worker threads; this
# collapses those into one Odoo download while staying fresh across requests.
_CREATIVES_MEMO: Dict[Tuple[str, str, bool, str, str], Tuple[float, List[Dict[str, object]]]] = {}
_CREATIVES_MEMO_LOCK = threading.Lock()
_CREATIVES_MEMO_TTL_SECONDS = 60.0


class EmployeeService:
    """Encapsulates employee search logic and formatting for the dashboard."""

    def __init__(self, client: OdooClient):
        self.client = client

    @classmethod
    def from_settings(cls, settings: OdooSettings) -> "EmployeeService":
        return cls(OdooClient(settings))

    def get_all_creatives(self, include_inactive: bool = True) -> List[Dict[str, object]]:
        """Fetch all creative employees (including inactive) for total count.

        Args:
            include_inactive: If True, includes inactive creatives. If False, only active.

        Returns:
            List of all creative employees
        """
        memo_key = (
            self.client.settings.url,
            self.client.settings.db,
            bool(include_inactive),
            (Config.DASHBOARD_CREATIVE_DEPARTMENTS or "").strip(),
            (Config.DASHBOARD_DEPARTMENT_SBU_FILTER or "").strip(),
        )
        now = time.monotonic()
        with _CREATIVES_MEMO_LOCK:
            entry = _CREATIVES_MEMO.get(memo_key)
            if entry is not None and (now - entry[0]) < _CREATIVES_MEMO_TTL_SECONDS:
                # Deep copy: callers enrich these dicts in place, so cached
                # records must never be handed out by reference.
                return copy.deepcopy(entry[1])

        creatives = self._fetch_all_creatives(include_inactive)

        with _CREATIVES_MEMO_LOCK:
            _CREATIVES_MEMO[memo_key] = (time.monotonic(), creatives)
        return copy.deepcopy(creatives)

    def _fetch_all_creatives(self, include_inactive: bool = True) -> List[Dict[str, object]]:
        """Download and normalize creative employees from Odoo (uncached)."""
        department_ids = self._get_target_department_ids()
        if not department_ids:
            return []

        domain = [
            ("department_id", "in", department_ids),
        ]

        # If include_inactive is False, filter to only active
        if not include_inactive:
            domain.append(("active", "=", True))
        
        # Base fields that should always exist
        base_fields = [
            "name",
            "user_id",
            "department_id",
            "work_email",
            "resource_calendar_id",
            "company_id",
            "x_studio_joining_date",
            "x_studio_rf_contract_end_date",
        ]
        
        # Current market fields
        current_market_fields = [
            "x_studio_market",
            "x_studio_start_date",
            "x_studio_end_date",
            "x_studio_pool",
        ]
        
        # Previous market fields (rf_ prefix has been removed from Odoo)
        previous_market_fields = [
            "x_studio_market_1",
            "x_studio_start_date_1",
            "x_studio_end_date_1",
            "x_studio_pool_1",
            "x_studio_market_2",
            "x_studio_start_date_2",
            "x_studio_end_date_2",
            "x_studio_pool_2",
            "x_studio_market_3",
            "x_studio_start_date_3",
            "x_studio_end_date_3",
            "x_studio_pool_3",
        ]

        # Business Unit / Sub Business Unit / Pod fields (introduced 2026-04-01).
        # Start/end dates use the _4..._7 numbering because _1..._3 are taken by
        # the legacy market/pool slots above.
        current_business_unit_fields = [
            "x_studio_business_unit",
            "x_studio_sub_business_unit",
            "x_studio_pod",
            "x_studio_start_date_4",
            "x_studio_end_date_4",
        ]
        previous_business_unit_fields = [
            "x_studio_business_unit_1",
            "x_studio_sub_business_unit_1",
            "x_studio_pod_1",
            "x_studio_start_date_5",
            "x_studio_end_date_5",
            "x_studio_business_unit_2",
            "x_studio_sub_business_unit_2",
            "x_studio_pod_2",
            "x_studio_start_date_6",
            "x_studio_end_date_6",
            "x_studio_business_unit_3",
            "x_studio_sub_business_unit_3",
            "x_studio_pod_3",
            "x_studio_start_date_7",
            "x_studio_end_date_7",
        ]

        schema = self._get_field_schema(
            base_fields,
            current_market_fields,
            previous_market_fields,
            current_business_unit_fields,
            previous_business_unit_fields,
        )
        fields_to_use = list(schema["fields_to_use"])
        has_current_market_fields = schema["has_current_market_fields"]
        has_previous_fields = schema["has_previous_fields"]
        has_current_business_unit_fields = schema["has_current_business_unit_fields"]
        has_previous_business_unit_fields = schema["has_previous_business_unit_fields"]
        bu_m2o_relations = dict(schema["bu_m2o_relations"])
        bu_m2m_relations = dict(schema["bu_m2m_relations"])

        creatives: List[Dict[str, object]] = []

        for batch in self.client.search_read_chunked(
            "hr.employee",
            domain=domain,
            fields=fields_to_use,
            order="name asc",
        ):
            if bu_m2o_relations:
                self._hydrate_studio_m2o_names(batch, bu_m2o_relations)
            if bu_m2m_relations:
                self._hydrate_studio_m2m_names(batch, bu_m2m_relations)
            for record in batch:
                department_display = None
                department_value = record.get("department_id") or []
                if isinstance(department_value, (list, tuple)) and len(department_value) >= 2:
                    department_display = department_value[1]

                calendar_value = record.get("resource_calendar_id") or []
                calendar_id = None
                calendar_name = None
                if isinstance(calendar_value, (list, tuple)) and len(calendar_value) >= 2:
                    calendar_id = calendar_value[0]
                    calendar_name = calendar_value[1]

                company_value = record.get("company_id") or []
                company_id = None
                company_name = None
                if isinstance(company_value, (list, tuple)) and len(company_value) >= 2:
                    company_id = company_value[0]
                    company_name = company_value[1]

                # Linked res.users id (used to join approval requests to employees).
                user_value = record.get("user_id") or []
                user_id = None
                if (
                    isinstance(user_value, (list, tuple))
                    and user_value
                    and isinstance(user_value[0], int)
                ):
                    user_id = user_value[0]

                # Parse current market fields (only if they exist)
                current_market = None
                current_start = None
                current_end = None
                current_pool = None
                
                if has_current_market_fields:
                    current_market = self._extract_market_name(record.get("x_studio_market"))
                    current_start = self._parse_odoo_date(record.get("x_studio_start_date"))
                    current_end = self._parse_odoo_date(record.get("x_studio_end_date"))
                    current_pool = self._extract_pool_name(record.get("x_studio_pool"))
                
                # Parse previous market fields (only if they exist)
                previous_market_1 = None
                previous_start_1 = None
                previous_end_1 = None
                previous_pool_1 = None
                previous_market_2 = None
                previous_start_2 = None
                previous_end_2 = None
                previous_pool_2 = None
                previous_market_3 = None
                previous_start_3 = None
                previous_end_3 = None
                previous_pool_3 = None
                
                if has_previous_fields:
                    previous_market_1 = self._extract_market_name(record.get("x_studio_market_1"))
                    previous_start_1 = self._parse_odoo_date(record.get("x_studio_start_date_1"))
                    previous_end_1 = self._parse_odoo_date(record.get("x_studio_end_date_1"))
                    previous_pool_1 = self._extract_pool_name(record.get("x_studio_pool_1"))

                    previous_market_2 = self._extract_market_name(record.get("x_studio_market_2"))
                    previous_start_2 = self._parse_odoo_date(record.get("x_studio_start_date_2"))
                    previous_end_2 = self._parse_odoo_date(record.get("x_studio_end_date_2"))
                    previous_pool_2 = self._extract_pool_name(record.get("x_studio_pool_2"))

                    previous_market_3 = self._extract_market_name(record.get("x_studio_market_3"))
                    previous_start_3 = self._parse_odoo_date(record.get("x_studio_start_date_3"))
                    previous_end_3 = self._parse_odoo_date(record.get("x_studio_end_date_3"))
                    previous_pool_3 = self._extract_pool_name(record.get("x_studio_pool_3"))

                # Parse current Business Unit slot (only if those fields exist).
                current_business_unit = None
                current_sub_business_unit = None
                current_pod = None
                current_bu_start = None
                current_bu_end = None

                if has_current_business_unit_fields:
                    current_business_unit = self._extract_pool_name(record.get("x_studio_business_unit"))
                    current_sub_business_unit = self._extract_pool_name(record.get("x_studio_sub_business_unit"))
                    current_pod = self._extract_pool_name(record.get("x_studio_pod"))
                    current_bu_start = self._parse_odoo_date(record.get("x_studio_start_date_4"))
                    current_bu_end = self._parse_odoo_date(record.get("x_studio_end_date_4"))

                # Parse previous Business Unit slots (only if those fields exist).
                previous_business_unit_1 = None
                previous_sub_business_unit_1 = None
                previous_pod_1 = None
                previous_bu_start_1 = None
                previous_bu_end_1 = None
                previous_business_unit_2 = None
                previous_sub_business_unit_2 = None
                previous_pod_2 = None
                previous_bu_start_2 = None
                previous_bu_end_2 = None
                previous_business_unit_3 = None
                previous_sub_business_unit_3 = None
                previous_pod_3 = None
                previous_bu_start_3 = None
                previous_bu_end_3 = None

                if has_previous_business_unit_fields:
                    previous_business_unit_1 = self._extract_pool_name(record.get("x_studio_business_unit_1"))
                    previous_sub_business_unit_1 = self._extract_pool_name(record.get("x_studio_sub_business_unit_1"))
                    previous_pod_1 = self._extract_pool_name(record.get("x_studio_pod_1"))
                    previous_bu_start_1 = self._parse_odoo_date(record.get("x_studio_start_date_5"))
                    previous_bu_end_1 = self._parse_odoo_date(record.get("x_studio_end_date_5"))

                    previous_business_unit_2 = self._extract_pool_name(record.get("x_studio_business_unit_2"))
                    previous_sub_business_unit_2 = self._extract_pool_name(record.get("x_studio_sub_business_unit_2"))
                    previous_pod_2 = self._extract_pool_name(record.get("x_studio_pod_2"))
                    previous_bu_start_2 = self._parse_odoo_date(record.get("x_studio_start_date_6"))
                    previous_bu_end_2 = self._parse_odoo_date(record.get("x_studio_end_date_6"))

                    previous_business_unit_3 = self._extract_pool_name(record.get("x_studio_business_unit_3"))
                    previous_sub_business_unit_3 = self._extract_pool_name(record.get("x_studio_sub_business_unit_3"))
                    previous_pod_3 = self._extract_pool_name(record.get("x_studio_pod_3"))
                    previous_bu_start_3 = self._parse_odoo_date(record.get("x_studio_start_date_7"))
                    previous_bu_end_3 = self._parse_odoo_date(record.get("x_studio_end_date_7"))

                creatives.append(
                    {
                        "id": record.get("id"),
                        "name": record.get("name"),
                        "user_id": user_id,
                        "department": department_display,
                        "email": record.get("work_email"),
                        "resource_calendar_id": calendar_id,
                        "resource_calendar_name": calendar_name,
                        "company_id": company_id,
                        "company_name": company_name,
                        "x_studio_joining_date": record.get("x_studio_joining_date"),
                        "x_studio_rf_contract_end_date": record.get("x_studio_rf_contract_end_date"),
                        # Current market fields
                        "current_market": current_market,
                        "current_market_start": current_start,
                        "current_market_end": current_end,
                        "current_pool": current_pool,
                        # Previous market 1 fields
                        "previous_market_1": previous_market_1,
                        "previous_market_1_start": previous_start_1,
                        "previous_market_1_end": previous_end_1,
                        "previous_pool_1": previous_pool_1,
                        # Previous market 2 fields
                        "previous_market_2": previous_market_2,
                        "previous_market_2_start": previous_start_2,
                        "previous_market_2_end": previous_end_2,
                        "previous_pool_2": previous_pool_2,
                        # Previous market 3 fields
                        "previous_market_3": previous_market_3,
                        "previous_market_3_start": previous_start_3,
                        "previous_market_3_end": previous_end_3,
                        "previous_pool_3": previous_pool_3,
                        # Current Business Unit slot (post-2026-04-01 model).
                        "current_business_unit": current_business_unit,
                        "current_sub_business_unit": current_sub_business_unit,
                        "current_pod": current_pod,
                        "current_business_unit_start": current_bu_start,
                        "current_business_unit_end": current_bu_end,
                        # Previous Business Unit slot 1.
                        "previous_business_unit_1": previous_business_unit_1,
                        "previous_sub_business_unit_1": previous_sub_business_unit_1,
                        "previous_pod_1": previous_pod_1,
                        "previous_business_unit_1_start": previous_bu_start_1,
                        "previous_business_unit_1_end": previous_bu_end_1,
                        # Previous Business Unit slot 2.
                        "previous_business_unit_2": previous_business_unit_2,
                        "previous_sub_business_unit_2": previous_sub_business_unit_2,
                        "previous_pod_2": previous_pod_2,
                        "previous_business_unit_2_start": previous_bu_start_2,
                        "previous_business_unit_2_end": previous_bu_end_2,
                        # Previous Business Unit slot 3.
                        "previous_business_unit_3": previous_business_unit_3,
                        "previous_sub_business_unit_3": previous_sub_business_unit_3,
                        "previous_pod_3": previous_pod_3,
                        "previous_business_unit_3_start": previous_bu_start_3,
                        "previous_business_unit_3_end": previous_bu_end_3,
                        # Keep tags for backward compatibility (will be empty or legacy)
                        "tags": [],
                    }
                )

        return self._apply_department_sbu_restrictions(creatives)

    @staticmethod
    def _apply_department_sbu_restrictions(
        creatives: List[Dict[str, object]],
    ) -> List[Dict[str, object]]:
        """Drop employees of restricted departments whose SBU doesn't match.

        DASHBOARD_DEPARTMENT_SBU_FILTER scopes mixed departments (e.g. Product
        hosts both a creative and a technical SBU; only the creative one
        belongs on this dashboard). An employee survives the restriction when
        ANY of their SBU assignment slots — current or previous, so people who
        moved SBUs keep their history — matches an allowed SBU.
        """
        restrictions = Config.department_sbu_filter()
        if not restrictions:
            return creatives
        # Local import: assignment_service has no dependency back on this
        # module, but keep the coupling out of import time regardless.
        from .assignment_service import split_assignment_field_tokens

        sbu_keys = (
            "current_sub_business_unit",
            "previous_sub_business_unit_1",
            "previous_sub_business_unit_2",
            "previous_sub_business_unit_3",
        )
        kept: List[Dict[str, object]] = []
        for creative in creatives:
            department = str(creative.get("department") or "").strip().lower()
            allowed = restrictions.get(department)
            if allowed is None:
                kept.append(creative)
                continue
            tokens: set[str] = set()
            for key in sbu_keys:
                tokens.update(
                    token.lower() for token in split_assignment_field_tokens(creative.get(key))
                )
            if tokens & allowed:
                kept.append(creative)
        return kept

    def get_creatives(self) -> List[Dict[str, object]]:
        """Fetch and normalize creative employees with their market information."""
        return self.get_all_creatives(include_inactive=False)

    def _get_field_schema(
        self,
        base_fields: List[str],
        current_market_fields: List[str],
        previous_market_fields: List[str],
        current_business_unit_fields: List[str],
        previous_business_unit_fields: List[str],
    ) -> Dict[str, Any]:
        """Return the probed field schema, cached process-wide per (url, db)."""
        cache_key = (self.client.settings.url, self.client.settings.db)
        now = time.monotonic()
        with _FIELD_SCHEMA_CACHE_LOCK:
            entry = _FIELD_SCHEMA_CACHE.get(cache_key)
            if entry is not None and (now - entry["cached_at"]) < _FIELD_SCHEMA_TTL_SECONDS:
                return entry

        entry = self._probe_field_schema(
            base_fields,
            current_market_fields,
            previous_market_fields,
            current_business_unit_fields,
            previous_business_unit_fields,
        )
        entry["cached_at"] = time.monotonic()

        # BU fields exist but relation discovery came back empty: that is the
        # signature of a transient fields_get failure, and caching it would pin
        # broken BU labels for the whole TTL. Serve it once, re-probe next call.
        discovery_incomplete = (
            entry["has_current_business_unit_fields"]
            and not entry["bu_m2o_relations"]
            and not entry["bu_m2m_relations"]
        )
        if not discovery_incomplete:
            with _FIELD_SCHEMA_CACHE_LOCK:
                _FIELD_SCHEMA_CACHE[cache_key] = entry
        return entry

    def _probe_field_schema(
        self,
        base_fields: List[str],
        current_market_fields: List[str],
        previous_market_fields: List[str],
        current_business_unit_fields: List[str],
        previous_business_unit_fields: List[str],
    ) -> Dict[str, Any]:
        """Probe Odoo for which optional Studio fields exist (uncached)."""
        # Test fields incrementally to determine which ones exist
        fields_to_use = base_fields.copy()
        has_current_market_fields = False
        has_previous_fields = False
        has_current_business_unit_fields = False
        has_previous_business_unit_fields = False

        # Test base fields first
        try:
            self.client.execute_kw(
                "hr.employee",
                "search_read",
                [[("id", ">", 0)]],
                {"fields": base_fields, "limit": 1}
            )
        except xmlrpc.client.Fault as e:
            # If base fields fail, something is seriously wrong
            error_str = str(e)
            if "Invalid field" in error_str:
                # Try with minimal fields
                fields_to_use = ["name", "department_id", "work_email"]
            else:
                raise

        # Test current market fields
        try:
            test_fields = base_fields + current_market_fields
            self.client.execute_kw(
                "hr.employee",
                "search_read",
                [[("id", ">", 0)]],
                {"fields": test_fields, "limit": 1}
            )
            fields_to_use = test_fields
            has_current_market_fields = True
        except xmlrpc.client.Fault as e:
            # Current market fields don't exist, use only base fields
            error_str = str(e)
            if "Invalid field" in error_str:
                # Keep only base fields
                pass
            else:
                raise

        # Test previous market fields (only if current market fields exist)
        # rf_ prefix has been removed from Odoo, so use pattern without rf_
        if has_current_market_fields:
            try:
                test_fields = fields_to_use + previous_market_fields
                self.client.execute_kw(
                    "hr.employee",
                    "search_read",
                    [[("id", ">", 0)]],
                    {"fields": test_fields, "limit": 1}
                )
                fields_to_use = test_fields
                has_previous_fields = True
            except xmlrpc.client.Fault as e:
                # Previous market fields don't exist, that's okay
                error_str = str(e)
                if "Invalid field" in error_str:
                    # Silently skip if fields don't exist
                    pass
                else:
                    raise

        # Test current Business Unit fields (introduced 2026-04-01).
        try:
            test_fields = fields_to_use + current_business_unit_fields
            self.client.execute_kw(
                "hr.employee",
                "search_read",
                [[("id", ">", 0)]],
                {"fields": test_fields, "limit": 1}
            )
            fields_to_use = test_fields
            has_current_business_unit_fields = True
        except xmlrpc.client.Fault as e:
            error_str = str(e)
            if "Invalid field" in error_str:
                pass
            else:
                raise

        # Test previous Business Unit fields (only if current BU fields exist).
        if has_current_business_unit_fields:
            try:
                test_fields = fields_to_use + previous_business_unit_fields
                self.client.execute_kw(
                    "hr.employee",
                    "search_read",
                    [[("id", ">", 0)]],
                    {"fields": test_fields, "limit": 1}
                )
                fields_to_use = test_fields
                has_previous_business_unit_fields = True
            except xmlrpc.client.Fault as e:
                error_str = str(e)
                if "Invalid field" in error_str:
                    pass
                else:
                    raise

        # Studio sub-models for BU/SBU/Pod often ship without a proper
        # display_name configuration, so Odoo's XML-RPC returns m2o values
        # as ``[id, str(id)]`` instead of ``[id, "Strategy & Insights"]``.
        # We discover the relation models once and resolve real names later
        # via a batched read.
        bu_field_names: List[str] = []
        if has_current_business_unit_fields:
            bu_field_names += [
                "x_studio_business_unit",
                "x_studio_sub_business_unit",
                "x_studio_pod",
            ]
        if has_previous_business_unit_fields:
            bu_field_names += [
                "x_studio_business_unit_1",
                "x_studio_sub_business_unit_1",
                "x_studio_pod_1",
                "x_studio_business_unit_2",
                "x_studio_sub_business_unit_2",
                "x_studio_pod_2",
                "x_studio_business_unit_3",
                "x_studio_sub_business_unit_3",
                "x_studio_pod_3",
            ]
        bu_m2o_relations: Dict[str, str] = {}
        bu_m2m_relations: Dict[str, str] = {}
        if bu_field_names:
            bu_m2o_relations, bu_m2m_relations = self._discover_bu_field_relations(bu_field_names)

        return {
            "fields_to_use": fields_to_use,
            "has_current_market_fields": has_current_market_fields,
            "has_previous_fields": has_previous_fields,
            "has_current_business_unit_fields": has_current_business_unit_fields,
            "has_previous_business_unit_fields": has_previous_business_unit_fields,
            "bu_m2o_relations": bu_m2o_relations,
            "bu_m2m_relations": bu_m2m_relations,
        }

    def _extract_market_name(self, market_field: Any) -> Optional[str]:
        """Extract market name from Odoo field (can be a list or string)."""
        if not market_field:
            return None
        if isinstance(market_field, (list, tuple)) and len(market_field) >= 2:
            result = str(market_field[1]).strip() if market_field[1] else None
            return result
        if isinstance(market_field, str):
            result = market_field.strip() if market_field.strip() else None
            return result
        return None
    
    def _extract_pool_name(self, pool_field: Any) -> Optional[str]:
        """Extract pool name from Odoo field (can be a list or string)."""
        if not pool_field:
            return None
        if isinstance(pool_field, str):
            return pool_field.strip() if pool_field.strip() else None
        if isinstance(pool_field, (list, tuple)) and pool_field:
            # Many2many: list of (id, name) records from search_read
            if all(isinstance(item, (list, tuple)) and len(item) >= 2 for item in pool_field):
                names: List[str] = []
                for item in pool_field:
                    label = item[1]
                    if label is None or label is False:
                        continue
                    t = str(label).strip()
                    if t and t not in names:
                        names.append(t)
                return ", ".join(names) if names else None
            # Many2many / x2m ID list only — cannot display without a separate read
            if all(isinstance(x, int) for x in pool_field):
                return None
            # Many2one [id, display_name]
            if len(pool_field) >= 2 and isinstance(pool_field[0], int) and isinstance(pool_field[1], str):
                return str(pool_field[1]).strip() if pool_field[1] else None
        return None

    def _discover_bu_field_relations(
        self, field_names: List[str]
    ) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Map BU/SBU/Pod field names to relation models via ``fields_get``.

        Studio stores BU/SBU/Pod as **many2many** (tags); older setups may use
        many2one. Returns ``(many2one_fields, many2many_fields)`` — each maps
        ``field_name -> relation_model`` (e.g. ``x_business_unit``).
        """
        if not field_names:
            return {}, {}
        try:
            meta = self.client.execute_kw(
                "hr.employee",
                "fields_get",
                [field_names],
                {"attributes": ["type", "relation"]},
            )
        except Exception:
            return {}, {}
        m2o: Dict[str, str] = {}
        m2m: Dict[str, str] = {}
        if isinstance(meta, dict):
            for fname, info in meta.items():
                if not isinstance(info, dict):
                    continue
                rel = info.get("relation")
                if not rel:
                    continue
                ftype = info.get("type")
                if ftype == "many2one":
                    m2o[fname] = rel
                elif ftype == "many2many":
                    m2m[fname] = rel
        return m2o, m2m

    def _hydrate_studio_m2o_names(
        self,
        batch: List[Dict[str, Any]],
        field_relations: Dict[str, str],
    ) -> None:
        """In-place: replace m2o tuples whose display_name is just ``str(id)``
        with the proper name read directly from the related model.

        Studio sub-models commonly lack a configured ``_rec_name``, so Odoo's
        default ``display_name`` falls back to the record id. This walks each
        m2o field, batches a read against the relation model, and rewrites
        affected tuples in the batch.
        """
        if not batch or not field_relations:
            return

        # Collect IDs per relation model.
        ids_by_relation: Dict[str, set[int]] = {}
        for record in batch:
            for fname, rel_model in field_relations.items():
                value = record.get(fname)
                if isinstance(value, (list, tuple)) and len(value) >= 1:
                    rec_id = value[0]
                    if isinstance(rec_id, int):
                        ids_by_relation.setdefault(rel_model, set()).add(rec_id)

        if not ids_by_relation:
            return

        # Read each relation once for the union of IDs across fields that share it.
        # Try the common Studio name fields first; fall back to display_name.
        names_by_relation: Dict[str, Dict[int, str]] = {}
        for rel_model, ids in ids_by_relation.items():
            try:
                rows = self.client.execute_kw(
                    rel_model,
                    "read",
                    [list(ids)],
                    {"fields": ["display_name", "x_name", "name"]},
                )
            except Exception:
                try:
                    rows = self.client.execute_kw(
                        rel_model,
                        "read",
                        [list(ids)],
                        {"fields": ["display_name"]},
                    )
                except Exception:
                    continue

            id_to_name: Dict[int, str] = {}
            for row in rows or []:
                rec_id = row.get("id")
                if not isinstance(rec_id, int):
                    continue
                # Prefer x_name (Studio convention), then name, then display_name.
                # Skip values that look like the bare id, since those are the
                # symptom we are trying to fix.
                resolved = (
                    self._real_name(row.get("x_name"))
                    or self._real_name(row.get("name"))
                    or self._real_name(row.get("display_name"))
                )
                if resolved:
                    id_to_name[rec_id] = resolved
            names_by_relation[rel_model] = id_to_name

        # Rewrite tuples in the batch.
        for record in batch:
            for fname, rel_model in field_relations.items():
                value = record.get(fname)
                if not isinstance(value, (list, tuple)) or not value:
                    continue
                rec_id = value[0]
                if not isinstance(rec_id, int):
                    continue
                resolved = names_by_relation.get(rel_model, {}).get(rec_id)
                if resolved:
                    record[fname] = [rec_id, resolved]

    def _hydrate_studio_m2m_names(
        self,
        batch: List[Dict[str, Any]],
        field_relations: Dict[str, str],
    ) -> None:
        """Expand many2many tag fields from ``search_read`` (list of ids) into
        ``[[id, display_name], ...]`` so ``_extract_pool_name`` can join labels.

        Without this, Odoo returns e.g. ``[12, 34]`` and we previously dropped
        them as \"no display\", so BU resolution saw empty slots.
        """
        if not batch or not field_relations:
            return

        ids_by_relation: Dict[str, set[int]] = {}
        for record in batch:
            for fname, rel_model in field_relations.items():
                value = record.get(fname)
                if not value or value is False:
                    continue
                if not isinstance(value, list):
                    continue
                for item in value:
                    if isinstance(item, int):
                        ids_by_relation.setdefault(rel_model, set()).add(item)
                    elif isinstance(item, (list, tuple)) and len(item) >= 1 and isinstance(
                        item[0], int
                    ):
                        ids_by_relation.setdefault(rel_model, set()).add(item[0])

        if not ids_by_relation:
            return

        names_by_relation: Dict[str, Dict[int, str]] = {}
        for rel_model, ids in ids_by_relation.items():
            try:
                rows = self.client.execute_kw(
                    rel_model,
                    "read",
                    [list(ids)],
                    {"fields": ["display_name", "x_name", "name"]},
                )
            except Exception:
                try:
                    rows = self.client.execute_kw(
                        rel_model,
                        "read",
                        [list(ids)],
                        {"fields": ["display_name"]},
                    )
                except Exception:
                    continue

            id_to_name: Dict[int, str] = {}
            for row in rows or []:
                rec_id = row.get("id")
                if not isinstance(rec_id, int):
                    continue
                resolved = (
                    self._real_name(row.get("x_name"))
                    or self._real_name(row.get("name"))
                    or self._real_name(row.get("display_name"))
                )
                if resolved:
                    id_to_name[rec_id] = resolved
                else:
                    id_to_name[rec_id] = f"#{rec_id}"
            names_by_relation[rel_model] = id_to_name

        for record in batch:
            for fname, rel_model in field_relations.items():
                value = record.get(fname)
                if not value or not isinstance(value, list):
                    continue
                ordered_ids: List[int] = []
                for item in value:
                    if isinstance(item, int):
                        ordered_ids.append(item)
                    elif isinstance(item, (list, tuple)) and len(item) >= 1 and isinstance(
                        item[0], int
                    ):
                        ordered_ids.append(item[0])
                if not ordered_ids:
                    continue
                id_to_name = names_by_relation.get(rel_model, {})
                record[fname] = [
                    [rid, id_to_name.get(rid, f"#{rid}")] for rid in ordered_ids
                ]

    @staticmethod
    def _real_name(value: Any) -> Optional[str]:
        """Treat numeric-string or empty values as 'no real name'."""
        if value is None or value is False:
            return None
        text = str(value).strip()
        if not text or text.isdigit():
            return None
        return text

    def _parse_odoo_date(self, value: Any) -> Optional[date]:
        """Parse a date value from Odoo."""
        if value is None:
            return None
        # False is expected from Odoo when date fields are empty
        if value is False:
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value).date()
            except ValueError:
                try:
                    return datetime.strptime(value, "%Y-%m-%d").date()
                except ValueError:
                    return None
        return None

    def _get_target_department_ids(self) -> List[int]:
        """Resolve hr.department ids for dashboard scope (Config DASHBOARD_CREATIVE_DEPARTMENTS).

        Each configured name is looked up in Odoo (case-insensitive exact match after fetch).
        Pools and markets come from each employee's Odoo fields.
        """
        raw = (Config.DASHBOARD_CREATIVE_DEPARTMENTS or "").strip()
        names = [p.strip() for p in raw.split(",") if p.strip()]
        if not names:
            names = ["Creative", "Creative Strategy"]

        seen: set[int] = set()
        out: List[int] = []

        for name in names:
            key = name.lower()
            # ilike on the full configured string finds the row without assuming a "creative" substring.
            # Filter to exact name so e.g. "Creative" does not pick "Creative Strategy".
            rows = self.client.search_read_all(
                "hr.department",
                domain=[("name", "ilike", name)],
                fields=["name", "id"],
            )
            for dept in rows:
                if dept.get("name", "").strip().lower() != key:
                    continue
                rid = dept.get("id")
                if isinstance(rid, int) and rid not in seen:
                    seen.add(rid)
                    out.append(rid)

        return out
