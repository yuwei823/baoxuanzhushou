"""Explicitly authored additional core obligations and article scope decisions.

Only the locally reviewed 50/39/83 article sets are supported. No new file or article
is auto-reviewed by this table; the application script requires exact coverage.
"""

PREFIXES = {
    "S": "insurance_sales_behavior_order_2023_02",
    "F": "financial_network_marketing_order_2026_09",
    "I": "internet_insurance_supervision_order_2020_13",
}


def ref(code):
    return f"{PREFIXES[code[0]]}::art_{int(code[1:]):03d}"


# id, article refs, scope, behavior, facts, exception, checkability
SPECS = [
    (
        "licensed_insurance_and_marketing_subject",
        "S3 I3 I23 I35 I65 F2",
        "insurance_sales_or_internet_business",
        "Insurance sales and internet insurance business require the specified institutional or personnel status and registration; distinguish advertising services from acting as an insurance seller or consultant.",
        "publisher role;license and registration evidence;actual activity;channel",
        "Institutional and personnel definitions differ by regulation. Missing credentials in a creative do not prove lack of qualification.",
        "external_verification",
    ),
    (
        "partner_contract_and_delegation",
        "S9 I34 I61 I64 I68 F20 F22 F25",
        "agency_or_third_party_cooperation",
        "Check written cooperation/mandate scope, permitted delegation, consumer disclosure and partner qualification for the applicable insurance or financial-marketing model.",
        "cooperation model;mandate contract;principal consent;partner license;delegation chain",
        "Internet insurance article 61 permits insurance intermediary re-delegation only with principal consent, disclosure and a qualified recipient. Bank agents and internet enterprise agents have separate no-redelegation duties in articles 64/68; do not conflate these models.",
        "external_verification",
    ),
    (
        "suitability_and_consumer_demand",
        "S21 S28 I17",
        "individual_insurance_sales",
        "Assess insurance need, risk, premium capacity and existing cover; when the specified mismatch, insufficient capacity or duplicate cover is found, advise stopping the purchase and explain risk if the consumer insists.",
        "consumer needs;risk and affordability assessment;existing cover;advice record;consumer choice",
        "Sales article 28 does not impose an unconditional refusal: a consumer who insists may proceed after the required risk explanation and confirmation of voluntary choice. A generic advertisement alone cannot prove this process.",
        "external_verification",
    ),
    (
        "truthful_health_disclosure_prompt",
        "S27 I17",
        "precontract_questionnaire_or_sales_flow",
        "Prompt truthful disclosure and its consequences; do not induce concealment of actual health conditions. Assess specific insurer questions rather than inventing an unlimited duty to disclose.",
        "complete questions;exact sales advice;material stage;consumer facts",
        "Sales article 27 limits the duty to the scope and content of questions except where law provides otherwise; a broad questionnaire item is allowed when it has specific content.",
        "context_required",
    ),
    (
        "policy_confirmation_and_approved_terms",
        "S29 S30",
        "insurance_contract_conclusion",
        "Use approved/filed insurance clauses and rates, and preserve the consumer's own lawful confirmation; sales staff must not confirm contract documents for the consumer.",
        "contract;approved clauses and rates;confirmation record;lawful written mandate",
        "Article 29 recognizes the policyholder or a person with a written mandate; telephone recording and internet traceable confirmation have channel-specific conditions. This is not proof of confirmation from an isolated advertisement.",
        "external_verification",
    ),
    (
        "premium_payment_and_accounts",
        "S32 I19 I40",
        "insurance_premium_or_benefit_payment",
        "Check the specified premium collection accounts and recipients; do not accept unauthorized staff handling of premium, refund or benefit transfers.",
        "payer and payee;account ownership;institutional collection arrangement;transaction record",
        "Internet insurance article 19 permits a cooperating intermediary's dedicated premium account. Article 40 permits contract-specified benefit accounts and specified refund accounts; do not treat every non-insurer payee as illicit.",
        "external_verification",
    ),
    (
        "personal_information_consent_and_use",
        "S7 I38 F27",
        "marketing_or_insurance_personal_data_use",
        "Personal information collection, processing, sharing and secondary use must satisfy the cited consent, authorization and security requirements.",
        "processing purpose;data and recipient;consent;legal basis;transfer and use records",
        "Apply the expressly stated legal exceptions and insurance-business necessity in the relevant article. A missing consent notice in a partial creative does not establish absence of actual consent.",
        "external_verification",
    ),
    (
        "unlawful_surrender_promotion",
        "S37 S39",
        "surrender_related_promotion",
        "Do not unlawfully promote, consult on or act for insurance surrender, induce surrender and disrupt the market; assess former personnel/intermediaries' harmful incitement under article 37 where that relationship is established.",
        "exact claim;service offered;publisher relationship;legal basis;harm and activity context",
        "A consumer's lawful cancellation or neutral education is not automatically illegal surrender promotion. Article 39's unlawfulness and article 37's relationship/harm conditions need evidence.",
        "context_required",
    ),
    (
        "official_platform_mandatory_information",
        "S14 S40 I12 I13 I60 I75 F9",
        "official_website_or_self_operated_platform",
        "Apply the page-specific product, institution, service/contact, territory, platform-disclosure and client-notification requirements; article 40 additionally requires precontract refund-condition and process prompts.",
        "complete page;platform type;publisher;product;precontract stage;applicable disclosure list",
        "An isolated advertisement is not necessarily the institutional official website, self-operated platform or client-notification page. Industry-association disclosure and linked information must be checked in their stated locations.",
        "context_required",
    ),
    (
        "offline_service_availability_disclosure",
        "I14 I17 I26",
        "internet_insurance_sales_or_detail_page",
        "Disclose whether service can be completed online and relevant local-service limitations; check explicit all-online claims against evidence of actual service capacity.",
        "complete sales page;offline steps;consumer location;branches and local partners;actual service capacity",
        "Article 26 treats partial offline steps differently from products whose listed change/preservation/surrender/claims functions cannot be completed online at all; absence of a local branch does not alone prove no permitted local service.",
        "context_required",
    ),
    (
        "voluntary_renewal_and_sales_choices",
        "I17 I21",
        "internet_insurance_purchase_or_renewal_flow",
        "Preserve genuine choice, do not impose default selection or restrict cancellation of auto-debit, and do not auto-renew renewable insurance without customer consent.",
        "complete interaction;default selection;auto-debit controls;consent;renewal terms",
        "A renewal benefit claim alone does not establish the actual consent process or whether renewal is automatic.",
        "context_required",
    ),
    (
        "intermediary_industry_name_and_brand",
        "I59 I70 F24",
        "intermediary_or_cooperation_marketing_page",
        "Identify the intermediary's industry subcategory clearly, avoid misleading insurer-like short names, keep financial provider brands identifiable and distinguish insurance from other products/services.",
        "publisher type;full page;name and logo;actual insurer and provider;cooperation context",
        "Article 59 applies to intermediaries' platforms and the specified technical/customer-service cooperation institutions, not automatically to a licensed insurer's full legal name.",
        "context_required",
    ),
    (
        "multi_product_display_separation",
        "F11 I70 I79",
        "internet_platform_with_multiple_product_categories",
        "Use separate display sections for multiple financial categories and keep non-insurance products/services distinct from internet insurance business.",
        "complete platform layout;product categories;provider and platform type",
        "A single insurance product creative cannot establish the whole platform's category layout; article 79's unapproved non-insurance financial products require separate licensing evidence.",
        "context_required",
    ),
    (
        "marketing_message_optout",
        "F13 I15",
        "direct_marketing_message_or_call",
        "Provide the specified refusal/unsubscribe choice and respect a recorded consumer refusal; do not infer refusal merely from the supplied message.",
        "message or call type;optout mechanism;refusal record;subsequent sending history",
        "A submitted one-off message cannot prove repeat sending after refusal; educational content still needs its actual commercial attributes assessed.",
        "context_required",
    ),
    (
        "popup_close_control",
        "F14",
        "internet_financial_marketing_popup",
        "A financial-marketing popup must visibly indicate its close control and support one-click closure.",
        "full popup;visible close control;actual interaction;financial marketing context",
        "A static image may establish visible control absence only if it is complete; it cannot alone prove the one-click control's behavior.",
        "context_required",
    ),
    (
        "algorithm_recommendation_controls",
        "F13",
        "algorithmic_financial_product_marketing",
        "Do not deploy algorithms inducing excessive consumption; provide a non-personalized option or convenient algorithm-recommendation shutdown option.",
        "algorithm use;model behavior;complete controls;consumer interaction",
        "Do not infer actual algorithmic personalization or excessive-consumption behavior from a static creative.",
        "external_verification",
    ),
    (
        "regulated_account_names_and_trademarks",
        "F18 F19",
        "financial_marketing_website_app_account_or_trademark",
        "Use financial-industry terms in regulated names and trademarks only within the relevant qualification/consent requirements.",
        "complete name or trademark;publisher qualification;regulatory consent;overall trademark meaning",
        "Article 19 excepts a trademark with a different overall meaning that is unlikely to mislead consumers about financial qualification; do not apply account-name rules to ordinary product-body wording.",
        "external_verification",
    ),
    (
        "third_party_sales_intervention",
        "F20 I23",
        "third_party_marketing_or_noninsurance_operator",
        "Check prohibited third-party intervention in financial product sale/contract/payment/suitability or interactive consultation, and non-insurance entities' prohibited insurance-business activities.",
        "platform type;qualification;actual service;purchase flow;consultation and payment activity",
        "Financial marketing service providers and licensed insurance intermediaries are different roles; establish status before applying a non-insurance or third-party prohibition.",
        "external_verification",
    ),
    (
        "paid_education_disguised_marketing",
        "F21",
        "institution_commissioned_third_party_education",
        "A financial institution or its staff must not pay a third-party platform to disguise financial-product marketing as investor education or courses.",
        "commercial nature;institutional commissioning;third-party platform;payment evidence",
        "Neutral insurance education without the stated commissioning/payment facts is not proven to violate this specific rule.",
        "external_verification",
    ),
    (
        "special_internet_insurance_business_scope",
        "I47 I52 I58 I64 I68",
        "internet_insurer_or_special_intermediary_model",
        "Apply internet insurer offline-sales prohibition and the exact institution/product/territory/delegation conditions for other insurers, intermediaries, bank agents and internet enterprises.",
        "institution subtype;license;product;territory;delegation;channel;current ancillary conditions",
        "Article 52 expressly allows specified regional extensions subject to further regulatory conditions. Article 64 includes specified banks without physical outlets as an exception; do not treat every out-of-region sale as unlawful.",
        "external_verification",
    ),
    (
        "nonbank_payment_marketing_options",
        "F12",
        "nonbank_payment_provider_interface",
        "Apply the nonbank payment institution's restrictions on listing or marketing the specified financial products as payment-tool options.",
        "publisher type;actual product type;complete payment options;marketing services",
        "Do not apply this publisher-specific restriction to every insurance advertisement containing a payment link.",
        "context_required",
    ),
    (
        "illegal_financial_activity_marketing",
        "F6 I79",
        "financial_marketing_or_insurance_self_operated_platform",
        "Do not market or facilitate unlawful financial activity; verify the status of non-insurance financial products offered by an insurance platform and apply special private-placement/OTC audience constraints only when relevant.",
        "actual financial activity;qualification;product approval;audience;channel;platform type",
        "Legality requires real qualification/product evidence; absence of disclosure does not itself prove illegal financial activity. Private-placement and OTC clauses do not automatically apply to insurance.",
        "external_verification",
    ),
    (
        "approved_marketing_content_use",
        "S18 F7 I15",
        "authorized_personnel_or_platform_publication",
        "Use institution-reviewed/approved marketing content as required, do not independently publish or alter it without authorization, and distinguish this from the authority to sell the product.",
        "publisher;approved content version;publication record;review and authorization records",
        "A creative alone cannot prove the institution never reviewed or authorized it.",
        "external_verification",
    ),
    (
        "internet_platform_operating_conditions",
        "I7 I8",
        "internet_insurance_institution_and_platform",
        "Verify platform/institution operating conditions and required stop/resume announcements when conditions fail or the platform ceases operation.",
        "institution type;filing;systems/security certificates;operating condition;announcements;timing",
        "Marketing material cannot establish actual IT/security compliance. Article 8 differentiates failure of conditions from a voluntary platform stop, whose announcement must be at least 20 working days in advance.",
        "external_verification",
    ),
]


def supplementary_cards():
    return [
        {
            "rule_id": rid,
            "article_ids": [ref(code) for code in refs.split()],
            "category": rid,
            "subject_scope": ["as_defined_by_cited_regulations"],
            "channel_scope": [scope],
            "product_scope": ["insurance_or_applicable_financial_product"],
            "trigger_conditions": [f"Establish {scope} and the cited subject conditions."],
            "prohibited_or_required_behavior": behavior,
            "exceptions": [exception],
            "required_facts": facts.split(";"),
            "checkability": checkability,
            "coverage_group": rid,
            "interpretation_note": (
                "Evaluate each cited clause's distinct conditions; unknown facts are unresolved, "
                "not proof of violation or compliance."
            ),
        }
        for rid, refs, scope, behavior, facts, exception, checkability in SPECS
    ]


# Each number is explicitly classified after reading the local full article.
# Unmapped articles outside the content demo retain a reason; no catch-all default.
SCOPE_GROUPS = {
    "S": [
        (
            "out_of_scope",
            [1, 2, 4, 5, 10, 43, 44, 45, 46, 47, 48, 49, 50],
            "目的、定义、适用范围、监管职责、法律责任或生效解释；保留作背景及关联依据，不独立作为营销内容违规。",
        ),
        (
            "out_of_scope",
            [6, 8, 12, 13, 15, 16, 20, 31, 41, 42],
            "周期公众教育、机构制度、信息系统、合同设计、能力分级、渠道监督、留痕、档案或监管报送；本 demo 不审核机构制度落实。",
        ),
        (
            "out_of_scope",
            [33, 34, 35, 36, 38],
            "销售后信息传递、保单发票、回访、离职服务通知及行业制度；超出提交营销材料的内容审核范围。",
        ),
        (
            "external_verification",
            [3, 7, 9, 11, 18, 21, 28, 29, 30, 32],
            "真实资质、授权、合作、消费者适当性、数据同意、签署、备案条款费率及资金交易需要外部记录；不能从素材缺项推断现实违规。",
        ),
        (
            "context_required",
            [14, 17, 19, 22, 23, 24, 25, 26, 27, 37, 39, 40],
            "含可审核宣传或披露义务；必须先确认主体、渠道、产品、页面/销售阶段、完整性及条文明示例外。",
        ),
    ],
    "F": [
        (
            "out_of_scope",
            [1, 3, 4, 26, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39],
            "背景定义、原则、监管分工、自律、处罚及解释生效条款；保留上下文，不依据泛化原则自动判单项内容违规。",
        ),
        ("out_of_scope", [23], "持续合作评估、整改及终止合作属于机构管理落实，营销文本无法证明。"),
        (
            "external_verification",
            [2, 6, 7, 16, 17, 18, 19, 20, 21, 22, 25, 27],
            "主体合法性、内容审批、人员许可、代言外部法律、名称商标资格、合作与数据使用需要真实外部证据；不足则待核验。",
        ),
        (
            "context_required",
            [5, 8, 9, 10, 11, 12, 13, 14, 15, 24],
            "按明确的金融网络营销、机构/平台、页面、发送方式、组合销售及产品条件审查；部分规则还需真实交互或外部事实。",
        ),
    ],
    "I": [
        (
            "out_of_scope",
            [1, 2, 4, 5, 6, 10, 11, 44, 50, 71, 72, 73, 74, 76, 77, 78, 80, 81, 82, 83],
            "定义、适用范围、一般管理、监管职责、过渡及生效解释条款；保留定义与关联规则，不独立判定广告内容。",
        ),
        (
            "out_of_scope",
            [9, 18, 24, 25, 33, 36, 37, 39, 41, 43, 46, 48, 51, 53, 54, 55, 56, 57, 62, 63, 66, 67],
            "产品开发、核保、IT安全、内部制度、资金合作结算、机构业务/系统运营、人员分工及统计报告；不在营销素材审核边界内。",
        ),
        (
            "out_of_scope",
            [20, 22, 27, 28, 29, 30, 31, 32, 42, 45, 49, 69],
            "售后回访、保单、保全理赔、退保服务及投诉机制；本 demo 不替代售后流程合规审核。",
        ),
        (
            "external_verification",
            [3, 7, 8, 16, 19, 23, 34, 35, 38, 40, 47, 52, 58, 64, 65, 68, 79],
            "经营/执业许可、平台所有权、业务条件、账户、委托范围、地域与数据使用，需要资质或真实业务记录。",
        ),
        (
            "context_required",
            [12, 13, 14, 15, 17, 21, 26, 59, 60, 61, 70, 75],
            "完整指定页面的宣传、披露、选择权、续保、服务说明、机构简称、客户告知和转委托披露；逐款区分内部制度与素材义务。",
        ),
    ],
}
