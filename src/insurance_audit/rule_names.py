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


# Review-item types and rule-specific evidence requests are UI metadata.  The
# raw values remain in ReviewItem for machine consumers and audit replay.
REVIEW_TYPE_DISPLAY_NAMES = {
    "needs_context": "需补充材料",
    "external_verification_required": "需外部核验",
    "unreadable_image": "图片内容无法完整识别",
    "limited_rule_scope": "初审范围提示",
    "context": "需补充背景信息",
}


RULE_REQUIRED_INFORMATION = {
    "marketing_truthful_and_not_misleading": ["宣传原文及完整上下文", "产品与发布渠道信息", "合同、数据等主张依据"],
    "insurance_benefit_uncertainty_and_risk": ["产品类型及收益计算依据", "保险合同相关条款", "完整风险提示及版式"],
    "identify_insurance_product_and_provider": ["产品名称", "承保机构与中介机构身份", "完整发布页面及渠道信息"],
    "disclose_material_policy_terms_and_restrictions": ["完整营销材料", "保险合同及产品说明", "免责、限制等重要条款"],
    "no_regulatory_guarantee_or_filing_endorsement": ["完整宣传文字与画面", "相关表述的出处和上下文", "审批或备案事实证明"],
    "public_figure_endorsement_external_review": ["推荐或代言的完整内容", "相关人物身份与角色证明", "广告合规审核材料"],
    "marketing_personnel_authorization_and_channel": ["发布者身份与岗位", "营销授权记录", "账号归属及销售去向"],
    "stop_sale_and_price_change_claims": ["产品及时间主张", "保险公司正式公告", "停售或调价依据"],
    "regional_and_third_party_marketing_scope": ["机构许可证及经营范围", "客户所在地区", "第三方平台角色与授权"],
    "bundled_financial_products_and_default_choice": ["完整操作流程", "页面默认状态", "单独购买选项及消费者提示"],
    "licensed_insurance_and_marketing_subject": ["发布者身份与角色", "许可证及登记证明", "实际营销活动与渠道"],
    "partner_contract_and_delegation": ["合作模式及委托协议", "委托方同意证明", "合作方资质及委托链条"],
    "suitability_and_consumer_demand": ["消费者需求分析记录", "风险承受能力与支付能力评估记录", "既有保障、销售建议及消费者选择记录"],
    "truthful_health_disclosure_prompt": ["完整健康问询内容", "销售人员实际提示", "材料所处销售阶段及消费者信息"],
    "policy_confirmation_and_approved_terms": ["保险合同", "经审批或备案的条款与费率", "投保确认记录及书面委托"],
    "premium_payment_and_accounts": ["付款人与收款人信息", "收款账户归属", "机构代收安排及交易记录"],
    "personal_information_consent_and_use": ["数据处理目的与范围", "接收方信息", "同意或其他合法依据及流转记录"],
    "unlawful_surrender_promotion": ["完整宣传内容", "服务提供方与保险机构关系", "业务依据及实际活动背景"],
    "official_platform_mandatory_information": ["完整页面", "平台及发布者类型", "产品信息与销售阶段", "应披露事项清单"],
    "offline_service_availability_disclosure": ["完整销售页面", "线下办理步骤", "客户地区、网点及合作方服务能力"],
    "voluntary_renewal_and_sales_choices": ["完整操作流程", "默认选项与自动扣款设置", "消费者同意及续保条款"],
    "intermediary_industry_name_and_brand": ["发布者类型", "完整页面及名称标识", "承保机构、服务方和合作关系"],
    "multi_product_display_separation": ["完整平台页面布局", "产品分类", "产品提供方与平台类型"],
    "marketing_message_optout": ["营销消息或电话记录", "退订或拒收方式", "拒收后的发送记录"],
    "popup_close_control": ["完整弹窗页面", "可见关闭入口", "实际交互及营销场景"],
    "algorithm_recommendation_controls": ["算法使用说明", "推荐逻辑与用户交互", "完整控制和关闭选项"],
    "regulated_account_names_and_trademarks": ["完整账号名称或商标", "发布者资质", "监管许可及商标整体含义"],
    "third_party_sales_intervention": ["平台类型与资质", "实际服务内容", "咨询、支付及购买流程"],
    "paid_education_disguised_marketing": ["内容的商业性质", "机构委托关系", "第三方平台及付费证明"],
    "special_internet_insurance_business_scope": ["机构类型与许可证", "产品、地域和渠道", "委托关系及适用经营条件"],
    "nonbank_payment_marketing_options": ["发布者类型", "实际产品类型", "完整支付选项及营销服务内容"],
    "illegal_financial_activity_marketing": ["实际金融活动", "机构资质与产品批准材料", "受众、渠道及平台类型"],
    "approved_marketing_content_use": ["发布者信息", "经审核内容版本", "发布、审核及授权记录"],
    "internet_platform_operating_conditions": ["机构类型与备案信息", "系统和安全证明", "运营条件、公告及时间信息"],
    "insurer_prohibited_deception_of_policyholder": ["完整陈述及上下文", "产品与目标受众", "该表述对投保决定的影响"],
    "insurer_prohibited_off_contract_benefit_promise": ["完整承诺内容", "保险合同相关条款", "产品及发布渠道"],
    "insurer_prohibited_unauthorized_sales_delegation": ["实际销售方身份", "销售资质及授权证明", "销售渠道"],
    "insurer_prohibited_false_information_release": ["完整宣传主张", "事实依据及可验证来源"],
    "intermediary_prohibited_deception_and_concealment": ["完整陈述及上下文", "产品与目标受众", "该表述对投保决定的影响"],
    "intermediary_prohibited_off_contract_benefit": ["完整承诺内容", "保险合同相关条款", "产品及发布渠道"],
    "intermediary_prohibited_coercion_and_misrepresentation": ["完整诱导或施压表述", "所声称的权力或身份", "产品及发布渠道"],
    "intermediary_prohibited_premium_misappropriation": ["付款对象与收款账户", "产品及发布渠道", "收款方与保险公司的关系"],
    "intermediary_prohibited_illegal_commission_seeking": ["所谋取利益的具体内容", "利益接收方", "其与保险业务的关系"],
    "insurer_format_clause_explanation_duty": ["完整合同条款", "免责或责任限制的披露与突出提示", "产品及发布渠道"],
    "insurer_prohibited_unfair_competition": ["完整比较或贬损表述", "明示或暗示的竞争方", "发布渠道"],
    "intermediary_qualification_requirement": ["从业人员身份", "从业资格证明", "发布或销售渠道"],
}


def display_names_for(rule_ids):
    """Return only labels used by the active ruleset, preserving its order."""

    return {rule_id: RULE_DISPLAY_NAMES.get(rule_id, rule_id) for rule_id in rule_ids}


def required_information_for(rule_ids):
    """Return localized evidence requests for rules in the active ruleset."""

    return {
        rule_id: RULE_REQUIRED_INFORMATION.get(rule_id, ["与该规则相关的证明材料"])
        for rule_id in rule_ids
    }
