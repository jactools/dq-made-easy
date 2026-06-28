# Join Conditions - Quick Reference Guide

## 📋 What Are Join Conditions?

Connect and validate data across multiple related tables/objects in a single rule.

**Example:** *"Verify all customer orders reference valid active customers"*

---

## ⚡ Quick Start (3 Steps)

### Step 1: Click "🔗 Define Joins" Button
Select this from the rule's action menu.

### Step 2: Configure Your Join
```
Left Data Object    →  Operator  →  Right Data Object
Customer[id]          =            Order[customer_id]
```

### Step 3: Click Save
Your joins are now part of the rule.

---

## 🔗 Join Type Selector

| Join Type | When to Use | Matches |
|-----------|------------|---------|
| **Inner Join** | Standard relationships | Records in BOTH objects |
| **Left Join** | Check main object data | Records from LEFT object |
| **Right Join** | Check related object data | Records from RIGHT object |
| **Full Join** | Need all records | Records from BOTH objects |

**Default:** Inner Join (recommended)

---

## 🔢 Join Operators

| Operator | Symbol | Use Case |
|----------|--------|----------|
| **Equal** | `=` | Standard relationships (IDs match) |
| **Not Equal** | `!=` | Exclude relationships |
| **Greater Than** | `>` | Amount/date comparisons |
| **Greater/Equal** | `>=` | Range validations |
| **Less Than** | `<` | Amount/date comparisons |
| **Less/Equal** | `&lt;=` | Range validations |

**Most common:** `=` (matches IDs)

---

## 📝 Configuration Template

```
Join Type: [Select]

Condition 1:
  Left Object: [Customer]
  Left Attribute: [customer_id]
  Operator: [=]
  Right Object: [Order]
  Right Attribute: [customer_id]

[+ Add Condition] [Remove]

[Save] [Cancel]
```

---

## 🧪 Testing Your Joins

### Run a Test
1. Click **🧪 Test Rule** button
2. Enter number of samples (e.g., 10)
3. Click **Run Test**

### Check Results
```
✅ All Tests Passed
   Records Tested: 10
   Success Rate: 100%
   
   Join Conditions Evaluation
   Matched Contexts: 8
```

**Matched Contexts** = How many joined records were found

---

## ✅ Success Checklist

- [ ] Join type selected (Inner/Left/Right/Full)
- [ ] Both data objects selected
- [ ] Both attributes selected
- [ ] Operator is appropriate for data type
- [ ] Rule expression includes the joined data
- [ ] Test runs with matched contexts > 0
- [ ] Success rate is acceptable

---

## ⚠️ Common Issues & Fixes

| Problem | Cause | Fix |
|---------|-------|-----|
| **Matched Contexts = 0** | No matching data | Check attribute values exist in both objects |
| **Join won't save** | Missing required field | Fill in all: object, attribute, operator, right object, right attribute |
| **Wrong operator** | Using `!=` for normal join | Use `=` for standard relationships |
| **Slow tests** | Too many samples | Start with 10, increase to 100 later |
| **Data type mismatch** | Comparing text to number | Ensure both attributes are same type |

---

## 📚 Full Documentation

See [DQ-2 Join Conditions User Guide](/docs/user-manuals/DQ-2_JOIN_CONDITIONS_USER_GUIDE/) for:
- Real-world examples by industry
- Advanced use cases
- Troubleshooting guide
- Best practices

---

## 🎯 Example: E-Commerce Order Validation

**Scenario:** "Orders must be from active customers"

```
Join Type: Inner Join

Condition 1:
  Order[customer_id] = Customer[customer_id]

Rule Expression:
  Customer.status = "active"
```

**Test Result:**
```
✅ 95 matched customer-order pairs tested
✅ 94 passed (98.9% success)
❌ 1 order from inactive customer
```

---

## 💡 Tips & Tricks

✅ **Do:**
- Start with Inner Join (simplest)
- Use `=` for ID relationships
- Test with 10+ samples
- Add descriptive rule name
- Monitor matched context count

❌ **Don't:**
- Create circular joins (A → B → A)
- Mix incompatible data types
- Use complex multi-step joins (start simple)
- Ignore low matched context counts
- Skip testing before activation

---

## 🚀 Next Steps

After configuring joins:

1. **Test** the rule with generated data
2. **Review** test results and join metrics
3. **Submit** for approval
4. **Activate** to monitor production
5. **Monitor** join evaluation in Operations

---

**Need Help?** Check the full [User Guide](/docs/user-manuals/DQ-2_JOIN_CONDITIONS_USER_GUIDE/) or contact your workspace admin.
