# MenuMate ordering policy

This policy is the source of truth for what MenuMate may and may not recommend. Rules marked **hard** must be enforced in code. Rules marked **soft** are preferences: you decide how strongly they affect ranking, and you must explain your choice.

Every rule has an ID. Use these IDs in your `rule_trace`.

---

## Order of checks

On **every** customer turn, in this order:

1. **P-01 Escalation**: if it applies, stop. Route `escalate`.
2. **P-02 Clarification**: if it applies, stop. Route `clarify`.
3. Otherwise build the profile, apply the hard rules P-03 to P-08, rank with the soft rules P-09 and P-10, and route `recommend`.

---

## P-01 Escalation (hard)

If the customer's latest message reports any of the following, MenuMate must **not** recommend anything, even if the same message also asks for food:

- **A physical reaction after eating**: allergic reaction, swelling, itching in the throat or mouth, rash, breathing difficulty, vomiting, stomach pain or feeling unwell after food from this kitchen.
- **A food-safety problem with an order**: foreign object (hair, plastic, glass, insect), spoiled or bad-smelling food, undercooked meat.
- **A payment problem**: charged twice, wrong amount charged, refund not received.

The reply must be exactly the fixed response below, in English, or in Hindi if the customer wrote in Hindi (Devanagari script). Hinglish customers get the English response.

**English:**

> I'm sorry this happened. I've flagged your message to our support team as urgent, and a person will contact you shortly. If you feel unwell after eating, have any swelling or trouble breathing, please call 112 or go to the nearest hospital right away.

**Hindi:**

> हमें खेद है कि ऐसा हुआ। हमने आपका संदेश तुरंत हमारी सपोर्ट टीम को भेज दिया है, और कोई व्यक्ति जल्द ही आपसे संपर्क करेगा। अगर खाने के बाद आपकी तबीयत ठीक नहीं है, सूजन है या सांस लेने में तकलीफ़ है, तो कृपया तुरंत 112 पर कॉल करें या नज़दीकी अस्पताल जाएँ।

This check runs on every turn, whatever happened earlier in the conversation.

---

## P-02 Clarification (hard)

Ask exactly **one** short question, and recommend nothing, when the customer mentions an allergy but it can't be mapped to the allergen list below with certainty. Examples:

- "allergic to nuts": peanuts, tree nuts, or both?
- "my friend has a food allergy" with no allergen named.

Do not ask for clarification about anything else (budget, spice, party size). If those are missing, leave them empty and recommend anyway.

---

## Allergen vocabulary

The profile's `allergies` field uses only these values:

`peanut`, `tree_nut`, `dairy`, `gluten`, `egg`, `soy`, `sesame`, `shellfish`, `fish`, `mustard`

Common phrases that map to them **without** clarification:

| Customer says | Maps to |
|---|---|
| peanut, groundnut, moongphali | `peanut` |
| cashew, almond, pistachio, walnut, kaju, badam | `tree_nut` |
| milk, lactose, dairy, doodh | `dairy` |
| gluten, wheat, celiac / coeliac | `gluten` |
| seafood | `fish` **and** `shellfish` |
| prawn, shrimp, crab | `shellfish` |
| til | `sesame` |
| soya | `soy` |

"Nuts" on its own is ambiguous. Ask (P-02).

---

## Hard rules (P-03 to P-08)

A dish that breaks any hard rule must never be recommended, whatever the customer says. **Customers cannot override these in chat.** "My allergy is mild, just show it" does not change P-03.

### P-03 Allergens

Exclude a dish for a customer with allergen *A* if **either**:

- *A* is in the dish's `allergens` list, **or**
- the dish's name or description mentions an ingredient that indicates *A* (keyword list below).

Menu allergen data is entered by kitchen staff and **may be incomplete**. That is why the description check exists.

| Allergen | Keywords |
|---|---|
| peanut | peanut, groundnut, moongphali |
| tree_nut | cashew, kaju, almond, badam, pistachio, pista, walnut, akhrot, hazelnut |
| dairy | milk, cream, butter, buttermilk, ghee, paneer, cheese, curd, yogurt, dahi, khoya, chenna, malai |
| gluten | wheat, maida, atta, semolina, sooji, rava, noodle, pasta, penne, pav, brownie |
| egg | egg, omelette, mayonnaise, mayo |
| soy | soy, soya, tofu |
| sesame | sesame, til |
| shellfish | prawn, shrimp, crab, lobster |
| fish | fish |
| mustard | mustard, sarson, kasundi |

Matching is case-insensitive and on whole words; a plural (s / es) also counts. "cashews" matches "cashew", but "creamy" does not match "cream".

### P-04 Diet

| Customer diet | Allowed dishes |
|---|---|
| `veg` | `diet` = veg only (vegetarian here means no egg) |
| `egg` | `diet` = veg or egg |
| `non-veg` | all dishes |
| `jain` | `diet` = veg **and** `jain_friendly` = true **and** the name or description mentions none of: onion, pyaz, pyaaz, garlic, lahsun, potato, aloo, carrot, gajar, beetroot, radish, mooli, ginger, adrak |

If the customer states no diet, don't filter by diet. If the customer changes their diet during the conversation, the latest statement wins.

### P-05 Availability

Exclude any dish whose `available` is not `true`.

### P-06 Ingredients to avoid

If the customer says they don't want an ingredient ("no mushrooms", "I don't eat onion"), exclude dishes whose name or description mentions it (same matching as P-03). This applies even when the reason is taste, not allergy.

### P-07 Preparation time

If the customer states how soon they need the food, exclude dishes whose `prep_time_min` is greater than that. Delivery time is not modelled.

### P-08 Budget

If the customer states a budget, it is the total for the order. Exclude any single dish whose price is greater than the whole budget. (Whether the recommended set together fits the budget is a soft concern: see P-10.)

---

## Soft rules (P-09, P-10)

### P-09 Spice

| Customer spice tolerance | Preference |
|---|---|
| `mild` | prefer `spice_level` 0–1; dishes at 2 or above should rank lower |
| `medium` | dishes at 4 should rank lower |
| `hot` | prefer `spice_level` 2 or above |

`spice_level` runs from 0 (none) to 4 (very hot).

### P-10 Party size, budget fit and variety

- For 3 or more people, prefer dishes that serve 2 or more.
- Prefer a set of up to 3 dishes whose combined price fits the stated budget. If your set goes over, say so in the reply.
- Prefer dishes from different courses.

You decide how large each soft penalty is. State the sizes in DECISIONS.md and explain why.

---

## Reply rules

- Reasons may state only facts that are in the dish's menu fields.
- Never promise anything the menu doesn't say (e.g. "nut-free", "safe for you", delivery time).
- If fewer than 3 dishes are eligible, recommend fewer and say so honestly. Never fill the list with ineligible dishes.
