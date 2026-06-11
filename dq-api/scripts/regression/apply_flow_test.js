const axios = require("axios");

async function run() {
  const base = process.env.API_URL || "http://localhost:4001";
  const client = axios.create({ baseURL: base, validateStatus: () => true });

  console.log("Login as u1");
  const login = await client.post("/login", { id: "u1" });
  if (login.status >= 300) {
    console.error("Login failed", login.status, login.data);
    process.exit(2);
  }
  const token = (login.data && login.data.token) || null;
  if (!token) {
    console.error("No token returned from login");
    process.exit(3);
  }
  client.defaults.headers.common["Authorization"] = `Bearer ${token}`;

  console.log("Fetch catalog attributes");
  const attrs = await client.get("/attributes-catalog");
  if (
    attrs.status !== 200 ||
    !Array.isArray(attrs.data) ||
    attrs.data.length === 0
  ) {
    console.error("Failed to fetch catalog attributes", attrs.status, attrs.data);
    process.exit(4);
  }
  const firstAttr = attrs.data[0];
  console.log("Using attribute id", firstAttr.id);

  console.log("Create rule");
  const ruleResp = await client.post("/rules", {
    name: "regression-generated-rule",
    description: "regression test",
  });
  if (ruleResp.status >= 300) {
    console.error("Create rule failed", ruleResp.status, ruleResp.data);
    process.exit(5);
  }
  const ruleId = ruleResp.data && ruleResp.data.id;
  if (!ruleId) {
    console.error("No rule id in response", ruleResp.data);
    process.exit(6);
  }

  console.log("Map attribute to rule");
  const mapResp = await client.post("/rule-attributes", {
    entries: [{ ruleId, attributeId: String(firstAttr.id) }],
  });
  if (mapResp.status >= 300) {
    console.error("Mapping failed", mapResp.status, mapResp.data);
    process.exit(7);
  }

  console.log("Create approval (new)");
  const appResp = await client.post("/approvals", { ruleId, status: "new" });
  if (appResp.status >= 300) {
    console.error("Create approval failed", appResp.status, appResp.data);
    process.exit(8);
  }

  console.log("Verify approval present");
  const approvals = await client.get("/approvals");
  if (approvals.status !== 200 || !Array.isArray(approvals.data)) {
    console.error("Failed to list approvals", approvals.status, approvals.data);
    process.exit(9);
  }
  const found = approvals.data.find((a) => String(a.ruleId) === String(ruleId));
  if (!found) {
    console.error("Approval for created rule not found");
    process.exit(10);
  }

  // Optional: verify generated rule is not present in public rule catalog
  if (process.env.CHECK_HIDE_GENERATED === "1") {
    console.log(
      "Checking /rules to ensure generated rule is hidden from catalog",
    );
    const rulesList = await client.get("/rules");
    if (rulesList.status === 200 && Array.isArray(rulesList.data)) {
      const present = rulesList.data.find(
        (r) => String(r.id) === String(ruleId),
      );
      if (present) {
        console.error(
          "Generated rule is present in /rules catalog (expected hidden)",
        );
        process.exit(11);
      }
    }
  }

  console.log("Regression apply-flow: SUCCESS");
}

run().catch((err) => {
  console.error("Unexpected error", err && err.stack ? err.stack : err);
  process.exit(1);
});
