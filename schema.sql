-- ============================================================================
--  +15 Partner Portal — Database Schema (SQLite3)
--  BANA 5140 Data Management — Final Project
--
--  Business domain: a back-office portal where businesses (tenants) located in
--  Calgary's +15 skywalk buildings manage their public listings and the
--  promotions shown to people navigating the skywalk.
--
--  Design notes:
--    * 7 entities in third normal form (3NF) — no repeating groups, no partial
--      or transitive dependencies.
--    * Every table has a surface INTEGER PRIMARY KEY (a stable, system-generated
--      surrogate key) so that business-facing values (names, emails) can change
--      without breaking foreign-key relationships.
--    * Referential integrity is enforced with FOREIGN KEY constraints.
--      PRAGMA foreign_keys = ON is set by the application on every connection
--      (SQLite does not enforce FKs by default).
--    * CHECK constraints and NOT NULL guard data integrity at the storage layer
--      so the database stays valid even if application validation is bypassed.
--    * Indexes back the foreign keys and the columns used by search / filters.
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ----------------------------------------------------------------------------
-- 1. building — the +15-connected buildings (reference data seeded from the
--    City of Calgary open "Plus 15" dataset). A partner leases space in one
--    building; a building hosts many partners.  (1 : many  building → partner)
-- ----------------------------------------------------------------------------
CREATE TABLE building (
    building_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL UNIQUE,        -- e.g. "Bankers Hall"
    address         TEXT,                           -- street address if known
    quadrant        TEXT    CHECK (quadrant IN ('SW','SE','NW','NE')),
    plus15_level    INTEGER NOT NULL DEFAULT 1      -- floor the +15 runs on (1 = +15)
                    CHECK (plus15_level BETWEEN 0 AND 5),
    latitude        REAL,
    longitude       REAL,
    is_active       INTEGER NOT NULL DEFAULT 1      -- 0 = removed from network
                    CHECK (is_active IN (0,1))
);

-- ----------------------------------------------------------------------------
-- 2. category — controlled vocabulary for the type of business. Kept in its own
--    table (rather than a free-text column on partner) to avoid duplicate /
--    inconsistent spellings and to allow the list to be governed centrally.
--    (1 : many  category → partner)
-- ----------------------------------------------------------------------------
CREATE TABLE category (
    category_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL UNIQUE,        -- e.g. "Food & Beverage"
    description     TEXT
);

-- ----------------------------------------------------------------------------
-- 3. partner — the core business entity: a tenant business with a public
--    listing in the +15 portal. References a building and a category.
--    (1 : many  partner → promotion, partner → lease, partner → hours)
-- ----------------------------------------------------------------------------
CREATE TABLE partner (
    partner_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    business_name   TEXT    NOT NULL,
    building_id     INTEGER NOT NULL,
    category_id     INTEGER NOT NULL,
    unit_number     TEXT,                           -- suite / unit within building
    contact_name    TEXT,
    contact_email   TEXT,
    contact_phone   TEXT,
    description     TEXT,                           -- short public blurb
    status          TEXT    NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','pending','suspended','closed')),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (building_id) REFERENCES building (building_id),
    FOREIGN KEY (category_id) REFERENCES category (category_id)
);

-- ----------------------------------------------------------------------------
-- 4. opening_hours — a partner's hours of operation, one row per weekday.
--    Separated from partner (instead of 7 columns) because hours are a
--    repeating group; this keeps partner in 1NF and lets a partner be open or
--    closed per day with distinct times.  (many : 1  hours → partner)
-- ----------------------------------------------------------------------------
CREATE TABLE opening_hours (
    hours_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    partner_id      INTEGER NOT NULL,
    day_of_week     INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6), -- 0=Mon
    open_time       TEXT,                           -- 'HH:MM' (NULL = closed)
    close_time      TEXT,
    is_closed       INTEGER NOT NULL DEFAULT 0 CHECK (is_closed IN (0,1)),
    UNIQUE (partner_id, day_of_week),               -- one row per partner per day
    FOREIGN KEY (partner_id) REFERENCES partner (partner_id) ON DELETE CASCADE
);

-- ----------------------------------------------------------------------------
-- 5. promotion — a marketing offer a partner runs (the value the portal shows
--    to skywalk users). Many promotions per partner over time.
--    (many : 1  promotion → partner)
-- ----------------------------------------------------------------------------
CREATE TABLE promotion (
    promotion_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    partner_id      INTEGER NOT NULL,
    title           TEXT    NOT NULL,
    details         TEXT,
    discount_pct    INTEGER CHECK (discount_pct BETWEEN 0 AND 100),
    start_date      TEXT    NOT NULL,               -- 'YYYY-MM-DD'
    end_date        TEXT    NOT NULL,
    is_featured     INTEGER NOT NULL DEFAULT 0 CHECK (is_featured IN (0,1)),
    CHECK (end_date >= start_date),                 -- no negative-length promos
    FOREIGN KEY (partner_id) REFERENCES partner (partner_id) ON DELETE CASCADE
);

-- ----------------------------------------------------------------------------
-- 6. lease — the commercial agreement under which a partner occupies space.
--    One active lease per partner in the MVP, but modelled as its own entity
--    because lease terms (rent, dates, status) are conceptually distinct from
--    the public listing and are managed by a different stakeholder (leasing).
--    (many : 1  lease → partner)
-- ----------------------------------------------------------------------------
CREATE TABLE lease (
    lease_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    partner_id      INTEGER NOT NULL,
    start_date      TEXT    NOT NULL,
    end_date        TEXT    NOT NULL,
    monthly_rent    REAL    CHECK (monthly_rent >= 0),
    status          TEXT    NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','expired','terminated')),
    CHECK (end_date >= start_date),
    FOREIGN KEY (partner_id) REFERENCES partner (partner_id) ON DELETE CASCADE
);

-- ----------------------------------------------------------------------------
-- 7. portal_user — staff accounts who administer the portal (the people doing
--    the CRUD). Demonstrates a second independent entity and supports the
--    optional authentication feature. Not related to partner by FK because a
--    user manages many partners across the whole portal.
-- ----------------------------------------------------------------------------
CREATE TABLE portal_user (
    user_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT    NOT NULL UNIQUE,
    full_name       TEXT    NOT NULL,
    email           TEXT    NOT NULL UNIQUE,
    role            TEXT    NOT NULL DEFAULT 'steward'
                    CHECK (role IN ('admin','steward','viewer')),
    password_hash   TEXT,                           -- werkzeug hash (optional auth)
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ----------------------------------------------------------------------------
-- Indexes — back the foreign keys and the search / filter columns so reads
-- stay fast as the tables grow (read performance is a non-functional req).
-- ----------------------------------------------------------------------------
CREATE INDEX idx_partner_building   ON partner (building_id);
CREATE INDEX idx_partner_category   ON partner (category_id);
CREATE INDEX idx_partner_name       ON partner (business_name);
CREATE INDEX idx_partner_status     ON partner (status);
CREATE INDEX idx_promotion_partner  ON promotion (partner_id);
CREATE INDEX idx_promotion_dates    ON promotion (start_date, end_date);
CREATE INDEX idx_hours_partner      ON opening_hours (partner_id);
CREATE INDEX idx_lease_partner      ON lease (partner_id);
