# GAB-Gen Regulatory Gap, Limitation & Verification Report

**Document Version:** 1.0.0  
**Effective Date:** 2026-10-20  
**Jurisdiction:** Sri Lanka, Western Province  
**Component:** GAB-Gen Component 1  
**Prohibition Notice:** No budget calculation, construction estimation, or financial optimization.

---

## 1. Executive Summary

This report establishes the explicit boundaries between **verifiable automated regulatory checks** and **mandatory human/statutory clearances**. In compliance with legal principles, automated algorithms can guarantee that a design respects geometric and statutory constraints, but **cannot grant legal planning permission**.

---

## 2. Inventory of Unverified or Site-Specific Information

The following statutory controls require site-specific clearance from authorities and cannot be determined purely from an uploaded survey plan:

1. **Statutory Street Lines & Road Widening Reserves:**
   - Under Section 52 of the Municipal Councils Ordinance and Section 14 of the UDA Law, street lines are declared by Gazette or formal Council resolution. Unless marked explicitly on the survey plan by a Licensed Surveyor or verified via local authority clearance certificate, the exact road widening line must be flagged as `requires_regulatory_verification`.
2. **Irrigation & Canal Reservations:**
   - SLLDC Act reservations (4.5m to 10.0m along urban drainage canals) and Irrigation Department reservations along rivers/waterways require certified canal edge coordinates.
3. **Paddy Land De-Gazetting:**
   - Agrarian Development Act No. 46 of 2000 prohibits construction on gazetted paddy fields without written permission from the Commissioner General of Agrarian Development. If land title designates "Wela" (paddy) or adjacent to canals, clearance is flagged.
4. **NBRO Geotechnical Clearance:**
   - Where site slope exceeds 11 degrees (e.g. mountainous portions of Padukka/Seethawaka or steep terrain), clearance from the National Building Research Organisation (NBRO) is legally mandatory.
5. **High-Tension Electricity Line Reservations:**
   - CEB requires a 10m to 30m building corridor under 33kV/132kV transmission lines.

---

## 3. Legal Disclaimers & Professional Sign-off Requirements

To ensure institutional compliance and protect developers and clients:

1. **Submission Drawings:**
   - Complete municipal submission requires architectural drawings signed by a **Chartered Architect (SLIA)**, structural stability certification by a **Chartered Structural Engineer (IESL)**, and site boundaries certified by a **Licensed Surveyor**.
2. **Algorithmic Role:**
   - ArchAI-Plan GAB-Gen functions as a **regulation-constrained design synthesizer** to produce verifiable preliminary planning proposals that prevent compliance rejections during official authority submission.
