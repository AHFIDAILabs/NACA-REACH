-- =============================================================================
-- NACA AI HIV Chatbot — Seed Data: Sample Facilities
-- =============================================================================
-- Sample facilities across pilot states + additional verified tertiary HIV service sites.
-- Added rows prioritise facilities with web-verifiable location details and evidence of HIV
-- related services or clinics. Where exact geo coordinates, walk-in policy, or operating hours
-- were not consistently verifiable from high quality public sources, NULL values are used.
-- =============================================================================

INSERT INTO facilities (
    facility_name, state, lga, address, location, latitude, longitude,
    phone_primary, services, operating_days, operating_hours,
    accepts_walk_in, accreditation_status, last_verified_date, data_source
) VALUES

-- ── FCT Abuja ───────────────────────────────────────────────────────────────
(
    'National Hospital Abuja',
    'FCT', 'AMAC',
    'Plot 132, Central District, Garki, Abuja',
    ST_SetSRID(ST_MakePoint(7.4951, 9.0579), 4326),
    9.0579, 7.4951,
    '+2349012345678',
    ARRAY['HTS','ART','PrEP','PEP','PMTCT','TB','Counselling']::service_type[],
    'Mon-Fri', '08:00-17:00',
    TRUE, 'Active', '2026-03-01', 'NACA'
),
(
    'Wuse District Hospital',
    'FCT', 'AMAC',
    'Wuse Zone 4, Abuja',
    ST_SetSRID(ST_MakePoint(7.4720, 9.0765), 4326),
    9.0765, 7.4720,
    '+2349012345679',
    ARRAY['HTS','ART','Counselling']::service_type[],
    'Mon-Sat', '08:00-16:00',
    TRUE, 'Active', '2026-03-01', 'NACA'
),

-- ── Lagos ───────────────────────────────────────────────────────────────────
(
    'Lagos University Teaching Hospital (LUTH)',
    'Lagos', 'Mushin',
    'Idi-Araba, Surulere, Lagos',
    ST_SetSRID(ST_MakePoint(3.3569, 6.5171), 4326),
    6.5171, 3.3569,
    '+2348012345680',
    ARRAY['HTS','ART','PrEP','PEP','PMTCT','VMMC','TB','Counselling']::service_type[],
    'Mon-Fri', '08:00-17:00',
    TRUE, 'Active', '2026-02-15', 'NACA'
),
(
    'Lagos Island Maternity Hospital',
    'Lagos', 'Lagos Island',
    'Broad Street, Lagos Island',
    ST_SetSRID(ST_MakePoint(3.3947, 6.4531), 4326),
    6.4531, 3.3947,
    '+2348012345681',
    ARRAY['HTS','ART','PMTCT','Counselling']::service_type[],
    'Mon-Sat', '08:00-16:00',
    TRUE, 'Active', '2026-02-15', 'PEPFAR'
),
(
    'Nigerian Institute of Medical Research (NIMR)',
    'Lagos', 'Yaba',
    'Edmund Crescent, Yaba, Lagos',
    ST_SetSRID(ST_MakePoint(3.3792, 6.5099), 4326),
    6.5099, 3.3792,
    '+2348012345682',
    ARRAY['HTS','ART','PrEP','TB']::service_type[],
    'Mon-Fri', '09:00-16:00',
    TRUE, 'Active', '2026-02-15', 'FMOH'
),

-- ── Kano ────────────────────────────────────────────────────────────────────
(
    'Aminu Kano Teaching Hospital',
    'Kano', 'Tarauni',
    'Zaria Road, Kano',
    ST_SetSRID(ST_MakePoint(8.5167, 11.9964), 4326),
    11.9964, 8.5167,
    '+2347012345683',
    ARRAY['HTS','ART','PrEP','PEP','PMTCT','TB','Counselling']::service_type[],
    'Mon-Fri', '08:00-16:00',
    TRUE, 'Active', '2026-03-01', 'NACA'
),
(
    'Murtala Muhammad Specialist Hospital',
    'Kano', 'Kano Municipal',
    'Hospital Road, Kano City',
    ST_SetSRID(ST_MakePoint(8.5242, 12.0022), 4326),
    12.0022, 8.5242,
    '+2347012345684',
    ARRAY['HTS','ART','Counselling']::service_type[],
    'Mon-Sat', '08:00-15:00',
    TRUE, 'Active', '2026-03-01', 'FMOH'
),

-- ── Rivers (Port Harcourt) ──────────────────────────────────────────────────
(
    'University of Port Harcourt Teaching Hospital',
    'Rivers', 'Obio-Akpor',
    'East-West Road, Choba, Port Harcourt',
    ST_SetSRID(ST_MakePoint(6.9101, 4.8667), 4326),
    4.8667, 6.9101,
    '+2348012345685',
    ARRAY['HTS','ART','PrEP','PEP','PMTCT','VMMC','TB','Counselling']::service_type[],
    'Mon-Fri', '08:00-17:00',
    TRUE, 'Active', '2026-02-01', 'PEPFAR'
),

-- ── Benue ───────────────────────────────────────────────────────────────────
(
    'Benue State University Teaching Hospital',
    'Benue', 'Makurdi',
    'Makurdi, Benue State',
    ST_SetSRID(ST_MakePoint(8.5391, 7.7337), 4326),
    7.7337, 8.5391,
    '+2347012345686',
    ARRAY['HTS','ART','PMTCT','Counselling']::service_type[],
    'Mon-Fri', '08:00-16:00',
    TRUE, 'Active', '2026-01-15', 'NACA'
),

-- ── Nasarawa ────────────────────────────────────────────────────────────────
(
    'Federal Medical Centre Keffi',
    'Nasarawa', 'Keffi',
    'Keffi, Nasarawa State',
    ST_SetSRID(ST_MakePoint(7.8735, 8.8492), 4326),
    8.8492, 7.8735,
    '+2348012345687',
    ARRAY['HTS','ART','PEP','TB','Counselling']::service_type[],
    'Mon-Fri', '08:00-16:00',
    TRUE, 'Active', '2026-01-15', 'FMOH'
),

-- ── Oyo (Ibadan) ────────────────────────────────────────────────────────────
(
    'University College Hospital (UCH) Ibadan',
    'Oyo', 'Ibadan North',
    'Queen Elizabeth Road, Mokola, Ibadan',
    ST_SetSRID(ST_MakePoint(3.9053, 7.4019), 4326),
    7.4019, 3.9053,
    '+2348012345688',
    ARRAY['HTS','ART','PrEP','PEP','PMTCT','VMMC','TB','Counselling']::service_type[],
    'Mon-Fri', '08:00-17:00',
    TRUE, 'Active', '2026-02-15', 'NACA'
),
(
    'Adeoyo Maternity Teaching Hospital',
    'Oyo', 'Ibadan South-East',
    'Yemetu, Ibadan',
    ST_SetSRID(ST_MakePoint(3.8963, 7.3931), 4326),
    7.3931, 3.8963,
    '+2348012345689',
    ARRAY['HTS','ART','PMTCT','Counselling']::service_type[],
    'Mon-Sat', '08:00-16:00',
    TRUE, 'Active', '2026-02-15', 'PEPFAR'
);

-- =============================================================================
-- Additional tertiary and specialist facilities added from web-verifiable sources
-- =============================================================================
INSERT INTO facilities (
    facility_name, state, lga, address, location, latitude, longitude,
    phone_primary, services, operating_days, operating_hours,
    accepts_walk_in, accreditation_status, last_verified_date, data_source
) VALUES
(
    'University of Abuja Teaching Hospital',
    'FCT', 'Gwagwalada',
    'University of Abuja Teaching Hospital, Gwagwalada, P.M.B. 228, Abuja, Nigeria',
    NULL,
    NULL, NULL,
    '+2347040045614',
    ARRAY['HTS','ART','PMTCT','TB','Counselling']::service_type[],
    NULL, NULL,
    NULL, 'Active', '2026-04-22', 'CDC and official hospital website'
),
(
    'University of Benin Teaching Hospital',
    'Edo', 'Egor',
    'P.M.B. 1111, Ugbowo Lagos Road, Benin City, Edo State, Nigeria',
    NULL,
    NULL, NULL,
    '+2349133000051',
    ARRAY['HTS','ART','Counselling']::service_type[],
    NULL, NULL,
    NULL, 'Active', '2026-04-22', 'Official hospital website'
),
(
    'University of Nigeria Teaching Hospital',
    'Enugu', 'Nkanu West',
    'University of Nigeria Teaching Hospital, Ituku/Ozalla, Enugu, Nigeria',
    NULL,
    NULL, NULL,
    '+2347031322008',
    ARRAY['HTS','ART','Counselling']::service_type[],
    'Daily', '24 Hours',
    NULL, 'Active', '2026-04-22', 'Official hospital website'
),
(
    'Jos University Teaching Hospital',
    'Plateau', 'Jos North',
    'JUTH Road, Off Lamingo Road, Jos, Plateau State, Nigeria',
    NULL,
    NULL, NULL,
    NULL,
    ARRAY['HTS','ART','PMTCT','TB','Counselling']::service_type[],
    NULL, NULL,
    NULL, 'Active', '2026-04-22', 'Official hospital website and HIV programme literature'
),
(
    'University of Maiduguri Teaching Hospital',
    'Borno', 'Maiduguri',
    'Bama Road, P.M.B. 1414, Maiduguri, Borno State, Nigeria',
    NULL,
    NULL, NULL,
    NULL,
    ARRAY['HTS','ART','PMTCT','Counselling']::service_type[],
    NULL, NULL,
    NULL, 'Active', '2026-04-22', 'Official hospital website and PMTCT literature'
),
(
    'Federal Teaching Hospital Gombe',
    'Gombe', 'Gombe',
    'Ashaka Road, 620261, Gombe, Gombe State, Nigeria',
    NULL,
    NULL, NULL,
    NULL,
    ARRAY['HTS','ART','Counselling']::service_type[],
    NULL, NULL,
    NULL, 'Active', '2026-04-22', 'Official hospital website and HIV clinic literature'
),
(
    'Federal Medical Centre Umuahia',
    'Abia', 'Umuahia North',
    'Aba Road, opposite Guaranty Trust Bank, Umuahia 440236, Abia State, Nigeria',
    NULL,
    NULL, NULL,
    '+2348038089468',
    ARRAY['HTS','ART','Counselling']::service_type[],
    'Mon-Fri', '08:00-16:00',
    NULL, 'Active', '2026-04-22', 'Official hospital website and HIV clinic literature'
),
(
    'Federal Medical Centre Yenagoa',
    'Bayelsa', 'Yenagoa',
    'Hospital Road, Ovom, Yenagoa, Bayelsa State, Nigeria',
    NULL,
    NULL, NULL,
    NULL,
    ARRAY['HTS','ART','Counselling']::service_type[],
    'Mon-Fri', '08:00-16:00',
    NULL, 'Active', '2026-04-22', 'Official hospital website'
),
(
    'University of Uyo Teaching Hospital',
    'Akwa Ibom', 'Uyo',
    'Abak Road, before Ikot Oku Ikono Junction, Uyo, Akwa Ibom State, Nigeria',
    NULL,
    NULL, NULL,
    '+2348037343628',
    ARRAY['HTS','ART','Counselling']::service_type[],
    NULL, NULL,
    NULL, 'Active', '2026-04-22', 'Official hospital website'
),
(
    'Federal Medical Centre Yola',
    'Adamawa', 'Yola South',
    'Lamido Zubairu Road, P.M.B. 2017, Bye-Pass Yola Town, Adamawa State, Nigeria',
    NULL,
    NULL, NULL,
    NULL,
    ARRAY['HTS','ART','Counselling']::service_type[],
    NULL, NULL,
    NULL, 'Active', '2026-04-22', 'Public procurement records and secondary facility directory'
),
(
    'Nnamdi Azikiwe University Teaching Hospital',
    'Anambra', 'Nnewi North',
    'Nnewi Onitsha Old Road, Nnewi, Anambra State, Nigeria',
    NULL,
    NULL, NULL,
    '+2349083895285',
    ARRAY['HTS','ART','Counselling']::service_type[],
    NULL, NULL,
    NULL, 'Active', '2026-04-22', 'Official hospital website'
);
