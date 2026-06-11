# Database Schema Change Checklist

Use this checklist whenever you make database schema changes.

## Quick Reference

```bash
# 1. Update version
./dq-db/scripts/update_schema_version.sh 1.1.0

# 2. Make your schema changes
vim dq-db/init/01_schema.sql

# 3. Document in version history
vim dq-db/DB_VERSION.md

# 4. Test changes
./scripts/stop_stack.sh
./scripts/start-containers.sh --seed-all

# 5. Commit everything
git add dq-db/
git commit -m "chore(db): update schema to v1.1.0 - add new table"
```

## Detailed Checklist

### Before Making Changes

- [ ] Review current schema version in `system_info.csv`
- [ ] Determine new version number (MAJOR.MINOR.PATCH)
- [ ] Check if changes are breaking (requires MAJOR bump)

### During Changes

- [ ] Run version update script: `./dq-db/scripts/update_schema_version.sh <version>`
- [ ] Make schema changes in `dq-db/init/01_schema.sql`
- [ ] Update seed data in `dq-db/mock-data/*.csv` if needed
- [ ] Add new section to `dq-db/DB_VERSION.md` with:
  - [ ] Version number and date
  - [ ] Description of changes
  - [ ] Why the change was made
  - [ ] Migration notes (if applicable)

### Testing

- [ ] Stop all containers: `./scripts/stop_stack.sh`
- [ ] Start fresh with new schema: `./scripts/start-containers.sh --seed-all`
- [ ] Verify database initialization succeeds
- [ ] Check system info in UI shows new version
- [ ] Test affected features in the application
- [ ] Run any existing tests

### Documentation

- [ ] Update `dq-db/README.md` if structure changed
- [ ] Update API documentation if endpoints affected
- [ ] Document breaking changes in CHANGELOG.md (if exists)
- [ ] Add migration guide for production deployments

### Commit

- [ ] Stage all database changes: `git add dq-db/`
- [ ] Write descriptive commit message:
  ```
  chore(db): update schema to v<version> - <short description>
  
  - Added/Modified: <details>
  - Reason: <why>
  - Breaking: <yes/no>
  ```
- [ ] Push changes and notify team if breaking

## Common Scenarios

### Adding a New Table (MINOR version bump)
```bash
./dq-db/scripts/update_schema_version.sh 1.1.0
# Edit 01_schema.sql, add CREATE TABLE
# Add seed CSV in mock-data/
# Document in DB_VERSION.md
```

### Adding a Column (MINOR version bump)
```bash
./dq-db/scripts/update_schema_version.sh 1.1.0
# Edit 01_schema.sql, add column to table
# Update relevant CSVs with new column
# Document in DB_VERSION.md
```

### Renaming a Column (MAJOR version bump - breaking)
```bash
./dq-db/scripts/update_schema_version.sh 2.0.0
# Edit 01_schema.sql, rename column
# Update all CSVs with new column name
# Document migration steps in DB_VERSION.md
# Update application code to use new column name
```

### Adding an Index (PATCH version bump)
```bash
./dq-db/scripts/update_schema_version.sh 1.0.1
# Edit 01_schema.sql, add CREATE INDEX
# Document in DB_VERSION.md
```

## Troubleshooting

**Q: I forgot to update the version before making changes**
A: Run the version script now, document retroactively in DB_VERSION.md

**Q: The version script failed**
A: Check that you're using semantic versioning format (X.Y.Z)

**Q: Database won't initialize after changes**
A: Check postgres logs: `docker logs dq-rulebuilder-db-1`

**Q: System info modal shows old version**
A: Hard refresh browser (Cmd+Shift+R), check system_info.csv was updated
