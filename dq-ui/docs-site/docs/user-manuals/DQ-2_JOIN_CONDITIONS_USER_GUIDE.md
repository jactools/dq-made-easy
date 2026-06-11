# Join Conditions Feature - User Guide

## Overview

**Join Conditions** enable you to create data quality rules that validate relationships between multiple data objects (tables, entities, or datasets). This feature allows you to define quality rules that ensure data consistency and integrity across related datasets.

### What are Join Conditions?

Join conditions specify **how two or more data objects relate to each other**. For example:
- A **Customer** table joined with an **Order** table on `customer_id`
- An **Employee** table joined with a **Department** table on `department_id`
- A **Product** table joined with **Inventory** records on `product_id`

Once joined, you can write rules that validate data across these relationships, such as:
- "Order totals should match the sum of line item amounts"
- "Employees must belong to an active department"
- "All products with inventory must have valid SKUs"

---

## Getting Started

### Step 1: Open the Rule Builder

1. Navigate to the **Rules** section in your workspace
2. Create a new rule or edit an existing one
3. In the rule details, you'll see the **🔗 Define Joins** action button

### Step 2: Define Join Conditions

1. Click the **🔗 Define Joins** button
2. A modal dialog will appear titled "Define Join Conditions"

### Step 3: Configure Your Join

The join configuration modal contains:

#### **Join Type Selector**
Choose how to join your data objects:
- **Inner Join** (default): Only records where both objects have matching conditions
- **Left Join**: Records from the left object, including non-matching right records
- **Right Join**: Records from the right object, including non-matching left records
- **Full Join**: All records from both objects

#### **Configure Join Predicates**

Each join condition consists of:

| Component | Description | Example |
|-----------|-------------|---------|
| **Left Data Object** | First data object being joined | `Customer`, `Employee`, `Order` |
| **Left Attribute** | Field from the left object | `customer_id`, `emp_id` |
| **Operator** | Comparison operator | `=`, `!=`, `>`, `>=`, `<`, `&lt;=` |
| **Right Data Object** | Second data object being joined | `Order`, `Department`, `Inventory` |
| **Right Attribute** | Field from the right object | `customer_id`, `dept_id` |

#### **Supported Join Operators**

| Operator | Meaning | Use Case |
|----------|---------|----------|
| `=` | Equal | Standard join condition |
| `!=` | Not Equal | Exclude specific relationships |
| `>` | Greater Than | Numeric comparisons (dates, amounts) |
| `>=` | Greater or Equal | Numeric range validations |
| `<` | Less Than | Numeric comparisons |
| `&lt;=` | Less or Equal | Numeric range validations |

### Step 4: Add Multiple Join Conditions

You can add multiple join predicates to create complex relationships:

1. Configure your first join predicate
2. Click **+ Add Condition** to add another
3. All conditions are combined with **AND** logic (all must be true)
4. Click **Remove** to delete a condition

### Step 5: Save Join Conditions

1. Review your join configuration
2. Click **Save** to apply the join conditions to your rule
3. A success message will confirm: "Join conditions updated (X condition(s))"

---

## Real-World Examples

### Example 1: Customer-Order Validation

**Scenario:** Ensure orders only belong to valid customers

**Join Configuration:**
```
Join Type: Inner Join
Condition 1:
  Left: Order.customer_id = Right: Customer.customer_id
```

**Rule Expression:**
```
Customer.status = "active"
```

**Result:** Only orders from active customers pass the validation

---

### Example 2: Multi-Condition Employee Data Quality

**Scenario:** Validate that employees belong to valid, active departments and have proper salary ranges

**Join Configuration:**
```
Join Type: Inner Join
Condition 1:
  Left: Employee.dept_id = Right: Department.dept_id
Condition 2:
  Left: Employee.salary >= Right: DepartmentSalaryGuideline.min_salary
```

**Rule Expression:**
```
Department.status = "active" AND Employee.salary <= DepartmentSalaryGuideline.max_salary
```

**Result:** Employees are validated across multiple related datasets

---

### Example 3: Inventory Consistency Check

**Scenario:** Products with inventory should have complete master data

**Join Configuration:**
```
Join Type: Left Join
Condition 1:
  Left: Product.product_id = Right: Inventory.product_id
```

**Rule Expression:**
```
(Inventory.quantity IS NULL) OR (Product.sku IS NOT NULL AND Product.status = "active")
```

**Result:** All products are checked; those with inventory must have valid master data

---

## Testing Rules with Joins

### Running a Join-Enabled Test

1. **Select your rule** from the Rules list
2. Click the **🧪 Test Rule** action button
3. In the Test Rule modal:
   - Enter the number of **samples to generate** (default: 10)
   - A blue notice appears if joins are configured:
     > *"ℹ️ This rule has join conditions. Test data will be generated for all involved data objects."*

### Understanding Test Results

When you run a test on a rule with joins, you'll see:

#### **Pass/Fail Status**
- ✅ **All Tests Passed**: All joined records validated successfully
- ❌ **Test Failures Detected**: Some records failed the rule expression

#### **Key Metrics**
| Metric | Meaning |
|--------|---------|
| **Records Tested** | Total number of records evaluated |
| **Success Rate** | Percentage of records passing the rule |
| **Coverage** | Percentage of rule conditions covered |

#### **Join Conditions Evaluation** (New!)
A dedicated section shows join-specific results:

| Item | Meaning |
|------|---------|
| **Matched Contexts** | How many joined record combinations were found and tested |
| **Join Rules** | Shows the join conditions that were evaluated |

**Example Output:**
```
Join Conditions Evaluation
  Matched Contexts: 87
  Join Rules:
    - Order[customer_id] = Customer[customer_id]
    - Order[status] = Active
```

This tells you:
- ✅ 87 order-customer combinations were found and matched
- ✅ Both join conditions were successfully applied
- ✅ Rule expression was evaluated on all 87 matched records

---

## Best Practices

### ✅ Do's

1. **Start with Inner Joins** for most scenarios (most restrictive, clearest results)
2. **Use consistent data types** in your join attributes (both should be customer IDs, dates, etc.)
3. **Test with realistic sample counts** (start with 10-20, increase to 100+ for confidence)
4. **Document your joins** in the rule description:
   - *"Validates orders from active customers; joins Order → Customer on customer_id"*
5. **Monitor Join Context counts** during testing:
   - High matched count = good data coverage
   - Low matched count = check your join conditions

### ❌ Don'ts

1. **Don't use joins for unrelated data** (they won't produce meaningful matches)
2. **Don't create circular joins** (Order → Customer → Order)
3. **Don't expect joins across different data sources** (joins are within a workspace)
4. **Don't leave joins undefined** after marking a rule as "join-enabled"
5. **Don't mix incompatible operators** (comparing TEXT with `>` usually doesn't make sense)

---

## Troubleshooting

### Issue: "No matching joined records"

**Causes:**
- Join attributes don't exist in the test data
- Join condition operator is too restrictive (e.g., `!=` instead of `=`)
- Data type mismatch (comparing text to number)

**Solution:**
1. Verify attribute names in the Join modal
2. Check sample data for actual values
3. Ensure attribute types match (both numbers, both dates, etc.)
4. Run a test with 50+ samples to increase match probability

---

### Issue: "Matched Contexts is 0"

**Causes:**
- No valid combinations of left and right data objects in test data
- Join condition values don't overlap between objects

**Solution:**
1. Check that test data includes both data objects
2. Verify values overlap (e.g., if joining on `customer_id`, both objects must have the same customer IDs)
3. Consider using a **Left Join** or **Full Join** for debugging
4. Add more samples to increase overlap probability

---

### Issue: Join condition not saving

**Causes:**
- Required fields (left object, operator, right object, right attribute) are missing
- Modal was closed without clicking Save

**Solution:**
1. Ensure all fields in each join predicate are filled
2. Click the **Save** button at the bottom of the modal
3. Wait for the success message before closing the modal

---

## Advanced Tips

### Debugging Join Logic

Use multiple conditions to isolate issues:

**Bad join (few matches):**
```
Condition: Order[status] = Shipped != ReturnRequest[status] = Pending
```

**Better join (clearer logic):**
```
Condition 1: Order[order_id] = ReturnRequest[order_id]
Condition 2: Order[status] = "Shipped"
```

### Comparing Across Joins

Use join operators beyond `=` for sophisticated validations:

**Scenario:** "Prices should never increase between regions"
```
Join Type: Inner Join
Condition: Product[region_A_price] >= Product[region_B_price]
```

**Scenario:** "Invoice amounts must match or exceed line item totals"
```
Join Type: Inner Join
Condition: Invoice[total] >= LineItem[sum_of_items]
```

---

## Success Criteria

A well-designed join condition should:

✅ Have **clear, documented purpose** (stated in rule description)
✅ Produce **matched contexts >= 5%** of test samples
✅ Use **consistent data types** across join attributes
✅ Result in **meaningful rule validation** (catches real data issues)
✅ **Complete testing in < 5 seconds** on typical datasets

---

## Examples by Industry

### E-Commerce
- **Order validation:** Orders joined with Customers and Products
- **Inventory accuracy:** Current inventory matched against shipping records
- **Pricing consistency:** Product prices across online/offline channels

### Healthcare
- **Patient records:** Patients joined with Appointments and Medical History
- **Medication safety:** Patient allergies matched against prescribed medications
- **Billing accuracy:** Claims matched against service delivery records

### Financial Services
- **Account integrity:** Accounts joined with Transactions and Holders
- **Fraud detection:** Customers joined with Transaction history and Risk profiles
- **Regulatory compliance:** Accounts matched against sanctions lists

### Manufacturing
- **Bill of Materials:** Parts joined with Inventory and Suppliers
- **Quality tracking:** Products joined with Test Results and Conformance records
- **Cost accounting:** Parts joined with Cost Centers and Cost data

---

## Need Help?

- **API Documentation:** See `/api/rules/:ruleId/test-with-generated-data` in the technical docs
- **Rule Expression Guide:** See [DQ-1 Rule Validation User Guide](/docs/user-manuals/DQ-1_RULE_VALIDATION_USER_GUIDE/) for supported filter-expression syntax
- **Data Objects:** Check your workspace's data catalog for available objects and attributes
- **Support:** Contact your workspace administrator for data modeling questions

---

## What's Next?

Once your join conditions are configured and tested:

1. **Submit for Approval** (if your organization requires it)
2. **Activate** the rule to start monitoring production data
3. **Monitor results** through the Data Quality Dashboard
4. **Iterate** based on false positives/negatives found in production

Happy rule building! 🚀
