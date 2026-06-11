-- Generated patch: populate users.external_id from mock-data/users.csv
-- Generated at UTC: 2026-03-30T23:21:04Z
BEGIN;
UPDATE users SET external_id = '3c8bb690-2c05-4358-923a-db6c7d791215' WHERE lower(email) = lower('dq-admin@jaccloud.nl') AND (external_id IS NULL OR external_id = '');
UPDATE users SET external_id = '6d0ef3d8-0077-409e-87eb-569a1cde4e78' WHERE lower(email) = lower('alice@jaccloud.nl') AND (external_id IS NULL OR external_id = '');
UPDATE users SET external_id = '56c45a70-69b6-4afb-9b04-9b0ea1faa741' WHERE lower(email) = lower('bob@jaccloud.nl') AND (external_id IS NULL OR external_id = '');
UPDATE users SET external_id = 'c3da7cb9-52b3-44da-aeab-bc3565aa576b' WHERE lower(email) = lower('charlie@jaccloud.nl') AND (external_id IS NULL OR external_id = '');
UPDATE users SET external_id = '6d4c64a8-01fd-4c15-8b6d-9ac7d3567853' WHERE lower(email) = lower('sofie@jaccloud.nl') AND (external_id IS NULL OR external_id = '');
UPDATE users SET external_id = '46218d48-c4ac-4c4b-9df7-2e26360c773e' WHERE lower(email) = lower('oliver@jaccloud.nl') AND (external_id IS NULL OR external_id = '');
UPDATE users SET external_id = '4f14e0c2-5df6-4468-a75f-d780f624bfad' WHERE lower(email) = lower('jan@jaccloud.nl') AND (external_id IS NULL OR external_id = '');
UPDATE users SET external_id = '1156ffea-8155-4c53-8015-72206b983337' WHERE lower(email) = lower('emma@jaccloud.nl') AND (external_id IS NULL OR external_id = '');
UPDATE users SET external_id = 'b1e301f1-e34f-4b4c-b303-7bc598f4ab7b' WHERE lower(email) = lower('william@jaccloud.nl') AND (external_id IS NULL OR external_id = '');
UPDATE users SET external_id = 'ead26079-fd70-4e3f-8abf-7d2ba68385aa' WHERE lower(email) = lower('maaike@jaccloud.nl') AND (external_id IS NULL OR external_id = '');
UPDATE users SET external_id = '67f01dee-c276-44d8-9d1d-e5de531d8045' WHERE lower(email) = lower('james@jaccloud.nl') AND (external_id IS NULL OR external_id = '');
UPDATE users SET external_id = 'c32b3d8e-6f59-42ba-a54a-9b78f186d072' WHERE lower(email) = lower('bram@jaccloud.nl') AND (external_id IS NULL OR external_id = '');
UPDATE users SET external_id = 'c9488506-1c34-459e-a6aa-422d6678ed71' WHERE lower(email) = lower('charlotte@jaccloud.nl') AND (external_id IS NULL OR external_id = '');
UPDATE users SET external_id = 'a34c91e0-e6be-4b9b-a6a8-2b58cd0f0801' WHERE lower(email) = lower('daan@jaccloud.nl') AND (external_id IS NULL OR external_id = '');
UPDATE users SET external_id = 'e872ea48-e77e-4263-9613-8a910ebc03ee' WHERE lower(email) = lower('olivia@jaccloud.nl') AND (external_id IS NULL OR external_id = '');
UPDATE users SET external_id = '81a3909b-21a7-4fb6-b097-ffe799d3b96e' WHERE lower(email) = lower('ruben@jaccloud.nl') AND (external_id IS NULL OR external_id = '');
UPDATE users SET external_id = 'bab54e05-1e84-4820-b8b6-9dbe081949e2' WHERE lower(email) = lower('fleur@jaccloud.nl') AND (external_id IS NULL OR external_id = '');
UPDATE users SET external_id = '198a7d29-9b54-410c-9878-2f016344b50a' WHERE lower(email) = lower('thomas@jaccloud.nl') AND (external_id IS NULL OR external_id = '');
UPDATE users SET external_id = '5f1e557a-e74d-4c72-beca-03b3cdf73368' WHERE lower(email) = lower('jacbeekers@jaccloud.nl') AND (external_id IS NULL OR external_id = '');
UPDATE users SET external_id = 'bc6b0410-6ae0-44a1-9dab-8dae4d37b326' WHERE lower(email) = lower('sophie@jaccloud.nl') AND (external_id IS NULL OR external_id = '');
UPDATE users SET external_id = '84db8cc9-747a-4100-aeac-62d10eb0298a' WHERE lower(email) = lower('retail-admin@jaccloud.nl') AND (external_id IS NULL OR external_id = '');
UPDATE users SET external_id = 'ac2e38af-aa47-4efe-956c-64b7abd0a1fc' WHERE lower(email) = lower('corporate-admin@jaccloud.nl') AND (external_id IS NULL OR external_id = '');
UPDATE users SET external_id = 'c18daee1-3bc1-472e-8470-994f8d6ad698' WHERE lower(email) = lower('demo-analyst@jaccloud.nl') AND (external_id IS NULL OR external_id = '');
UPDATE users SET external_id = '7d3f584a-18a4-40d4-85ae-ce3f37687a0f' WHERE lower(email) = lower('demo-data-steward@jaccloud.nl') AND (external_id IS NULL OR external_id = '');
UPDATE users SET external_id = '590fd730-d3c0-42b5-b0de-052c77c92315' WHERE lower(email) = lower('demo-viewer@jaccloud.nl') AND (external_id IS NULL OR external_id = '');
COMMIT;
