"""Stable Chinese display names for the published audit rule IDs.

Rule IDs remain the machine-readable contract.  These names are presentation
metadata, so adding or revising a label does not mutate an immutable corpus
snapshot or invalidate its hash.
"""

RULE_DISPLAY_NAMES = {
    "marketing_truthful_and_not_misleading": "营销内容真实准确",
    "insurance_benefit_uncertainty_and_risk": "保险收益不确定性与风险提示",
    "identify_insurance_product_and_provider": "保险产品与承保机构标识",
    "disclose_material_policy_terms_and_restrictions": "重要保单条款与限制披露",
    "no_regulatory_guarantee_or_filing_endorsement": "禁止借监管审核或备案背书",
    "public_figure_endorsement_external_review": "公众人物代言合规核验",
    "marketing_personnel_authorization_and_channel": "营销人员授权与发布渠道",
    "stop_sale_and_price_change_claims": "停售与价格变动宣传",
    "regional_and_third_party_marketing_scope": "经营地域与第三方营销范围",
    "bundled_financial_products_and_default_choice": "捆绑销售与默认勾选",
    "licensed_insurance_and_marketing_subject": "保险销售与营销主体资质",
    "partner_contract_and_delegation": "合作协议与委托范围",
    "suitability_and_consumer_demand": "适当性与消费者需求",
    "truthful_health_disclosure_prompt": "健康信息如实告知提示",
    "policy_confirmation_and_approved_terms": "保单确认与报备条款使用",
    "premium_payment_and_accounts": "保费支付与收款账户",
    "personal_information_consent_and_use": "个人信息授权与使用",
    "unlawful_surrender_promotion": "非法退保宣传与代理",
    "official_platform_mandatory_information": "官方平台必备信息披露",
    "offline_service_availability_disclosure": "线下服务能力披露",
    "voluntary_renewal_and_sales_choices": "自主续保与销售选择",
    "intermediary_industry_name_and_brand": "中介机构名称与品牌标识",
    "multi_product_display_separation": "多类金融产品分区展示",
    "marketing_message_optout": "营销信息退订与拒收",
    "popup_close_control": "营销弹窗一键关闭",
    "algorithm_recommendation_controls": "算法推荐与关闭选项",
    "regulated_account_names_and_trademarks": "金融账号名称与商标使用",
    "third_party_sales_intervention": "第三方介入销售限制",
    "paid_education_disguised_marketing": "付费教育包装营销",
    "special_internet_insurance_business_scope": "互联网保险特殊经营范围",
    "nonbank_payment_marketing_options": "非银行支付渠道营销限制",
    "illegal_financial_activity_marketing": "非法金融活动营销",
    "approved_marketing_content_use": "经审核营销内容使用",
    "internet_platform_operating_conditions": "互联网平台运营条件",
    "insurer_prohibited_deception_of_policyholder": "保险人禁止欺骗投保人",
    "insurer_prohibited_off_contract_benefit_promise": "保险人禁止合同外利益承诺",
    "insurer_prohibited_unauthorized_sales_delegation": "保险人禁止无资质委托销售",
    "insurer_prohibited_false_information_release": "保险人禁止发布虚假信息",
    "intermediary_prohibited_deception_and_concealment": "中介禁止欺骗与隐瞒",
    "intermediary_prohibited_off_contract_benefit": "中介禁止合同外利益承诺",
    "intermediary_prohibited_coercion_and_misrepresentation": "中介禁止胁迫诱导与造假",
    "intermediary_prohibited_premium_misappropriation": "中介禁止侵占挪用保费",
    "intermediary_prohibited_illegal_commission_seeking": "中介禁止谋取不正当利益",
    "insurer_format_clause_explanation_duty": "格式条款提示与说明义务",
    "insurer_prohibited_unfair_competition": "保险人禁止不正当竞争",
    "intermediary_qualification_requirement": "保险中介从业资格要求",
}


def display_names_for(rule_ids):
    """Return only labels used by the active ruleset, preserving its order."""

    return {rule_id: RULE_DISPLAY_NAMES.get(rule_id, rule_id) for rule_id in rule_ids}
