"""Build reviewable rule-card candidates from the locally extracted core texts.

Cards remain unverified until legal mapping review is completed.
"""

import json
from pathlib import Path

from build_extraction_registry import build_registry

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data/corpus/official-v1-2026-10-11"

CARDS = [
    {
        "rule_id": "marketing_truthful_and_not_misleading",
        "article_ids": [
            "insurance_sales_behavior_order_2023_02::art_017",
            "financial_network_marketing_order_2026_09::art_008",
            "financial_network_marketing_order_2026_09::art_010",
            "internet_insurance_supervision_order_2020_13::art_015",
        ],
        "category": "misleading_or_exaggerated_claim",
        "subject_scope": ["insurance_institution", "insurance_intermediary", "marketing_personnel"],
        "channel_scope": ["all_marketing", "internet"],
        "product_scope": ["insurance", "financial_product_network_marketing"],
        "trigger_conditions": ["material makes a factual product, benefit, or comparison claim"],
        "prohibited_or_required_behavior": "Claims and comparisons must not be false, exaggerated, materially misleading, based on inaccurate information, or omit material assumptions or restrictions.",
        "exceptions": ["Apply only the clauses whose subject and channel conditions are met."],
        "required_facts": ["exact claim and surrounding context", "product and channel", "material completeness", "supporting contract or data when the claim depends on it"],
        "checkability": "context_required",
        "coverage_group": "content_truthfulness",
        "interpretation_note": "Keyword presence alone is insufficient; assess negation, quotation, educational context, support, and whether the claim is material.",
    },
    {
        "rule_id": "insurance_benefit_uncertainty_and_risk",
        "article_ids": [
            "insurance_sales_behavior_order_2023_02::art_022",
            "financial_network_marketing_order_2026_09::art_010",
            "internet_insurance_supervision_order_2020_13::art_014",
            "internet_insurance_supervision_order_2020_13::art_015",
        ],
        "category": "guaranteed_or_misrepresented_benefit",
        "subject_scope": ["insurance_institution", "insurance_intermediary", "marketing_personnel"],
        "channel_scope": ["all_marketing", "internet"],
        "product_scope": ["new_type_life_insurance", "insurance", "asset_management_product"],
        "trigger_conditions": ["material states or depicts benefits, returns, losses, or uncertainty"],
        "prohibited_or_required_behavior": "Do not overstate insurance responsibility or product returns, promise non-guaranteed returns, or omit uncertainty and related risk notices where required.",
        "exceptions": ["The exact rule depends on the product type and whether a stated benefit is contractually guaranteed."],
        "required_facts": ["product type", "benefit source and calculation basis", "contract wording", "risk notices", "material completeness"],
        "checkability": "context_required",
        "coverage_group": "benefit_and_risk",
        "interpretation_note": "Distinguish guaranteed contractual benefits from non-guaranteed illustrations; unknown contract terms require review.",
    },
    {
        "rule_id": "identify_insurance_product_and_provider",
        "article_ids": [
            "insurance_sales_behavior_order_2023_02::art_017",
            "insurance_sales_behavior_order_2023_02::art_024",
            "internet_insurance_supervision_order_2020_13::art_014",
            "internet_insurance_supervision_order_2020_13::art_015",
            "financial_network_marketing_order_2026_09::art_010",
        ],
        "category": "product_or_provider_identity_disclosure",
        "subject_scope": ["insurance_institution", "insurance_intermediary", "marketing_personnel"],
        "channel_scope": ["internet", "non_face_to_face"],
        "product_scope": ["insurance"],
        "trigger_conditions": ["material promotes an insurance product or service"],
        "prohibited_or_required_behavior": "Clearly identify the material as insurance promotion and display applicable product and provider identities required for the relevant channel and page type.",
        "exceptions": ["Specific display duties depend on whether the material is an internet insurance sales/detail page or another form of promotion."],
        "required_facts": ["channel", "page type", "product name", "insurer and intermediary identities", "material completeness"],
        "checkability": "context_required",
        "coverage_group": "identity_and_product_disclosure",
        "interpretation_note": "A stand-alone cropped image may not establish whether required identity information is absent from the complete page.",
    },
    {
        "rule_id": "disclose_material_policy_terms_and_restrictions",
        "article_ids": [
            "insurance_sales_behavior_order_2023_02::art_014",
            "insurance_sales_behavior_order_2023_02::art_025",
            "insurance_sales_behavior_order_2023_02::art_026",
            "financial_network_marketing_order_2026_09::art_008",
            "internet_insurance_supervision_order_2020_13::art_014",
        ],
        "category": "material_terms_or_restrictions_omitted",
        "subject_scope": ["insurance_institution", "insurance_intermediary", "marketing_personnel"],
        "channel_scope": ["official_online_platform", "internet_sales_or_detail_page", "precontract_sales"],
        "product_scope": ["insurance"],
        "trigger_conditions": ["material is a product explanation, sales/detail page, or precontract disclosure governed by the cited clause"],
        "prohibited_or_required_behavior": "Present material product information consistently with contract terms and provide the disclosures or explanations required at the applicable stage.",
        "exceptions": ["Precontract duties do not automatically apply to every isolated awareness advertisement."],
        "required_facts": ["page or sales stage", "full material", "contract and product explanation", "whether exclusions or limitations are relevant"],
        "checkability": "context_required",
        "coverage_group": "terms_and_restrictions",
        "interpretation_note": "Do not infer omission from a partial screenshot or short-form promotion unless the rule requires the item on that material itself.",
    },
    {
        "rule_id": "no_regulatory_guarantee_or_implied_endorsement",
        "article_ids": [
            "insurance_sales_behavior_order_2023_02::art_017",
            "financial_network_marketing_order_2026_09::art_010",
            "financial_network_marketing_order_2026_09::art_017",
            "internet_insurance_supervision_order_2020_13::art_015",
        ],
        "category": "regulatory_or_public_figure_endorsement",
        "subject_scope": ["marketing_entity", "marketing_personnel"],
        "channel_scope": ["all_marketing"],
        "product_scope": ["insurance", "financial_product"],
        "trigger_conditions": ["material invokes a regulator, filing/approval procedure, regulator staff, or public figure as a product assurance or recommendation"],
        "prohibited_or_required_behavior": "Do not imply that regulatory review or filing guarantees a product, or use regulatory bodies or staff as commercial endorsement; public-figure endorsements must follow applicable advertising requirements.",
        "exceptions": ["Neutral factual reporting of an approval or filing is not automatically an endorsement; context matters."],
        "required_facts": ["exact wording and imagery", "context and attribution", "approval or filing facts", "whether a public figure endorsement is present"],
        "checkability": "context_required",
        "coverage_group": "endorsement_and_regulatory_claims",
        "interpretation_note": "Do not infer a real endorsement or identity from an image alone.",
    },
    {
        "rule_id": "marketing_personnel_authorization_and_channel",
        "article_ids": [
            "insurance_sales_behavior_order_2023_02::art_018",
            "internet_insurance_supervision_order_2020_13::art_015",
            "internet_insurance_supervision_order_2020_13::art_016",
            "financial_network_marketing_order_2026_09::art_016",
        ],
        "category": "promotion_authorization_or_channel",
        "subject_scope": ["insurance_institution", "marketing_personnel", "third_party_platform"],
        "channel_scope": ["internet", "official_or_authorized_account", "live_or_short_video"],
        "product_scope": ["insurance", "financial_product"],
        "trigger_conditions": ["material is published by an individual or platform through a regulated marketing channel"],
        "prohibited_or_required_behavior": "Required personnel, institutional authorization, account, and self-operated platform conditions must be met for the applicable channel.",
        "exceptions": ["Applicability depends on the actual publisher, account, channel, and whether a purchase link or transaction is provided."],
        "required_facts": ["publisher identity and role", "authorization record", "account ownership", "sales flow and destination"],
        "checkability": "external_verification",
        "coverage_group": "authorization_and_channel",
        "interpretation_note": "A name or credential absent from submitted creative does not prove the person lacks authorization.",
    },
    {
        "rule_id": "stop_sale_and_price_change_claims",
        "article_ids": ["insurance_sales_behavior_order_2023_02::art_019"],
        "category": "unsupported_urgency_or_price_change_claim",
        "subject_scope": ["insurance_sales_personnel"],
        "channel_scope": ["all_sales"],
        "product_scope": ["insurance"],
        "trigger_conditions": ["sales personnel claim that a product will soon stop selling or its price will change"],
        "prohibited_or_required_behavior": "Before the insurer issues the required announcement, sales personnel must not claim in sales that the product is about to stop selling or its price is about to change.",
        "exceptions": ["The price adjustment exception and announcement conditions in the article apply."],
        "required_facts": ["speaker role", "product and timing claim", "insurer announcement", "adjustment basis"],
        "checkability": "context_required",
        "coverage_group": "urgency_and_scarcity",
        "interpretation_note": "A generic deadline or promotion is not automatically within this article without the specified product stop-sale/price-change claim.",
    },
    {
        "rule_id": "regional_and_third_party_marketing_scope",
        "article_ids": [
            "insurance_sales_behavior_order_2023_02::art_011",
            "insurance_sales_behavior_order_2023_02::art_017",
            "internet_insurance_supervision_order_2020_13::art_003",
            "internet_insurance_supervision_order_2020_13::art_005",
            "financial_network_marketing_order_2026_09::art_005",
        ],
        "category": "business_scope_or_region_mismatch",
        "subject_scope": ["insurance_institution", "insurance_intermediary", "third_party_platform"],
        "channel_scope": ["internet", "all_marketing"],
        "product_scope": ["insurance", "financial_product"],
        "trigger_conditions": ["material or sales flow indicates a regulated institution, service region, or delegated platform"],
        "prohibited_or_required_behavior": "Marketing and business must remain within licensed scope, permitted service region, and the financial institution's authorized third-party scope.",
        "exceptions": ["Specific territorial conditions differ by institution, product, and online business model."],
        "required_facts": ["institution license and scope", "customer region", "platform role and authorization", "whether the activity constitutes internet insurance business"],
        "checkability": "external_verification",
        "coverage_group": "institution_scope_and_region",
        "interpretation_note": "Cannot be cleared or found violated from creative alone when licensing, delegated scope, or customer location is unknown.",
    },
    {
        "rule_id": "bundled_financial_products_and_default_choice",
        "article_ids": [
            "insurance_sales_behavior_order_2023_02::art_023",
            "financial_network_marketing_order_2026_09::art_015",
        ],
        "category": "forced_bundle_or_default_opt_in",
        "subject_scope": ["insurance_institution", "financial_institution", "third_party_platform"],
        "channel_scope": ["sales_flow", "internet"],
        "product_scope": ["insurance", "financial_product_bundle"],
        "trigger_conditions": ["two or more insurance/financial products or services are presented as a bundle or default selection"],
        "prohibited_or_required_behavior": "Do not force bundling or make a combined financial-product purchase the default consent choice; provide the required prominent reminder.",
        "exceptions": ["The exact scope depends on whether the products are legally combined or the consumer can independently choose."],
        "required_facts": ["complete interaction flow", "default state", "separate purchase options", "consumer notice"],
        "checkability": "context_required",
        "coverage_group": "bundling_and_choice",
        "interpretation_note": "A static banner alone may not reveal whether a default selection or forced purchase exists.",
    },
]

article_path = CORPUS / "articles.jsonl"
articles = {
    json.loads(line)["article_id"]
    for line in article_path.read_text(encoding="utf-8").splitlines()
}
for card in CARDS:
    missing = sorted(set(card["article_ids"]) - articles)
    if missing:
        raise ValueError(f"{card['rule_id']} refers to missing articles: {missing}")
    card["verified"] = False
    card["verification_status"] = "candidate_pending_legal_mapping_review"
    card["ruleset_id"] = "official-v1-2026-10-11"

target = CORPUS / "rule_cards.jsonl"
target.write_text(
    "".join(json.dumps(card, ensure_ascii=False) + "\n" for card in CARDS),
    encoding="utf-8",
)
build_registry()
print(f"Wrote {target.relative_to(ROOT)}: {len(CARDS)} unverified candidate cards")
