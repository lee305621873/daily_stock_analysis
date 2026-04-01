# -*- coding: utf-8 -*-
"""Configurable stock screener scope definitions."""

from __future__ import annotations

from typing import Any, Dict, List

from src.data.stock_screener_cn_special_board_data import (
    CN_CPO_FALLBACK_CODES,
    CN_OPTICAL_CHIP_FALLBACK_CODES,
    CN_PCB_FALLBACK_CODES,
)


ScopeConfig = Dict[str, Any]
BoardConfig = Dict[str, Any]


STOCK_SCREENER_SCOPE_CONFIG: Dict[str, List[ScopeConfig]] = {
    "cn": [
        {
            "key": "all_market",
            "label": "A 股全市场",
            "description": "扫描全部 A 股标的；范围最大，建议配合扫描上限使用。",
            "kind": "full_market",
        },
        {
            "key": "cn_board_industry_dynamic",
            "label": "A 股行业板块（自定义）",
            "description": "从真实 A 股行业板块目录中选择一个行业，并按该行业完整成分股扫描。",
            "kind": "board_dynamic",
            "board_type": "industry",
        },
        {
            "key": "cn_board_concept_dynamic",
            "label": "A 股概念板块（自定义）",
            "description": "从真实 A 股概念板块目录中选择一个概念，并按该概念完整成分股扫描。",
            "kind": "board_dynamic",
            "board_type": "concept",
        },
        {
            "key": "cn_semiconductor",
            "label": "A 股半导体",
            "description": "优先从 A 股半导体板块实时获取成分股，失败时回退到维护清单。",
            "kind": "board",
            "board_type": "industry",
            "board_name": "半导体",
            "fallback_codes": [
                "603986", "688041", "688012", "688008", "300661", "300223", "600584", "002371",
                "600703", "688981", "300458", "688126", "002049", "600460", "688120", "002156",
                "300782", "603501", "688361", "300327",
            ],
        },
        {
            "key": "cn_cpo",
            "label": "A 股CPO",
            "description": "基于搜狐 CPO 概念页与同花顺共封装光学(CPO)公开成分股维护，优先使用缓存与实时板块结果。",
            "kind": "board",
            "board_type": "concept",
            "board_name": "CPO",
            "fallback_codes": CN_CPO_FALLBACK_CODES,
        },
        {
            "key": "cn_pcb",
            "label": "A 股PCB",
            "description": "基于搜狐 PCB 概念页与同花顺 PCB 概念公开成分股维护，优先使用缓存与实时板块结果。",
            "kind": "board",
            "board_type": "concept",
            "board_name": "PCB",
            "fallback_codes": CN_PCB_FALLBACK_CODES,
        },
        {
            "key": "cn_optical_chip",
            "label": "A 股光芯片",
            "description": "公开站点缺少统一“光芯片”板块名时，按搜狐光通信/光电子/光纤光缆/光学/激光概念与同花顺光纤概念并集维护，并参考东方财富光通信相关概念目录。",
            "kind": "board",
            "board_type": "concept",
            "board_name": "光芯片",
            "fallback_codes": CN_OPTICAL_CHIP_FALLBACK_CODES,
        },
        {
            "key": "cn_ai",
            "label": "A 股人工智能",
            "description": "优先从人工智能概念板块拉取成分股，覆盖算力、光模块和 AI 应用。",
            "kind": "board",
            "board_type": "concept",
            "board_name": "人工智能",
            "fallback_codes": [
                "000977", "002230", "300308", "603019", "688256", "688041", "300502", "300394",
                "601138", "002415", "300033", "300496", "300251", "688111", "002152", "300339",
                "603881", "002261", "300624", "688018",
            ],
        },
        {
            "key": "cn_new_energy",
            "label": "A 股新能源车",
            "description": "优先从新能源车概念板块拉取成分股，失败时回退到龙头清单。",
            "kind": "board",
            "board_type": "concept",
            "board_name": "新能源车",
            "fallback_codes": [
                "300750", "002594", "601012", "300274", "002460", "300014", "600438", "002466",
                "603799", "600732", "300750", "603659", "002709", "002850", "300457", "300568",
                "603806", "002812", "300073", "300118",
            ],
        },
        {
            "key": "cn_consumer",
            "label": "A 股消费龙头",
            "description": "优先从白酒板块拉取核心消费股，适合防守和高股息消费观察。",
            "kind": "board",
            "board_type": "industry",
            "board_name": "白酒",
            "fallback_codes": [
                "600519", "000858", "002304", "603288", "600887", "000568", "002714", "000333",
                "600690", "002311", "603369", "600600", "603345", "600559", "600809", "000596",
                "603317", "600298", "603719", "000729",
            ],
        },
        {
            "key": "cn_chemical",
            "label": "A 股化工",
            "description": "合并基础化工、化肥、氟化工、磷化工、煤化工、盐化工和电子化学品等板块成分股。",
            "kind": "board",
            "board_type": "industry",
            "board_name": "化工",
            "fallback_codes": [
                "300665", "300522", "300243", "300910", "688179", "001369", "605488", "920225",
                "300798", "300927", "300796", "300230", "300920", "920866", "001359", "001358",
                "001255", "301373", "300641", "603790",
            ],
        },
        {
            "key": "cn_oil_gas",
            "label": "A 股油气",
            "description": "合并石油石化、天然气、油气勘探、油气存储、油气改革、油气管网和页岩气等板块成分股。",
            "kind": "board",
            "board_type": "industry",
            "board_name": "油气",
            "fallback_codes": [
                "600339", "002629", "600968", "300055", "002408", "300164", "603619", "600800",
                "002207", "000703", "002986", "603798", "601808", "002554", "002221", "601857",
                "600346", "300839", "000637", "600938",
            ],
        },
        {
            "key": "cn_agriculture",
            "label": "A 股农业",
            "description": "合并农林牧渔、生态农业、生物农药、农机和智慧农业等板块成分股。",
            "kind": "board",
            "board_type": "industry",
            "board_name": "农业",
            "fallback_codes": [
                "002321", "000048", "300999", "603151", "002891", "920964", "002124", "001366",
                "002696", "000592", "920403", "600127", "300511", "600467", "920023", "002688",
                "300138", "002069", "603336", "600737",
            ],
        },
        {
            "key": "cn_consumption",
            "label": "A 股消费",
            "description": "合并商贸零售、旅游酒店、纺织服饰、美容护理和白酒等消费相关板块成分股。",
            "kind": "board",
            "board_type": "industry",
            "board_name": "消费",
            "fallback_codes": [
                "002072", "603214", "002127", "300592", "000419", "600280", "002818", "600287",
                "601366", "600539", "600729", "002697", "000564", "600865", "605136", "002277",
                "600327", "300518", "600128", "301078",
            ],
        },
        {
            "key": "cn_food",
            "label": "A 股食品",
            "description": "合并食品饮料、休闲食品、啤酒、国产乳业和白酒等食品饮料相关板块成分股。",
            "kind": "board",
            "board_type": "industry",
            "board_name": "食品",
            "fallback_codes": [
                "603156", "603345", "002726", "300997", "002626", "603866", "002329", "002461",
                "300908", "000858", "000568", "000848", "002515", "300915", "002820", "002719",
                "002695", "300146", "000596", "600530",
            ],
        },
        {
            "key": "cn_innovative_drug",
            "label": "A 股创新药",
            "description": "优先从创新药板块拉取成分股，覆盖创新药研发、CXO 和创新药产业链公司。",
            "kind": "board",
            "board_type": "industry",
            "board_name": "创新药",
            "fallback_codes": [
                "002728", "002262", "688177", "688176", "002793", "300725", "600479", "300723",
                "920017", "600721", "301263", "000566", "300436", "300147", "600535", "688443",
                "300434", "002923", "000597", "603229",
            ],
        },
        {
            "key": "custom_pool",
            "label": "自定义股票池",
            "description": "手动输入 A 股代码，适合扫描你自己的观察名单。",
            "kind": "custom_pool",
        },
    ],
    "hk": [
        {
            "key": "hk_board_industry_dynamic",
            "label": "港股行业板块（自定义）",
            "description": "从后端维护的港股行业池中选择一个行业，并按该行业代表成分股扫描。",
            "kind": "board_dynamic",
            "board_type": "industry",
        },
        {
            "key": "hk_tech",
            "label": "港股科技互联网",
            "description": "聚焦港股互联网平台、硬科技和软件服务龙头。",
            "kind": "preset_pool",
            "codes": [
                "00700", "09988", "03690", "01810", "09888", "09618", "01024", "06618", "09999", "09868",
                "09626", "02382", "02018", "00268", "09660", "00981", "02318", "09961", "03888", "09863",
            ],
        },
        {
            "key": "hk_finance",
            "label": "港股金融蓝筹",
            "description": "聚焦港股银行、保险、交易所和综合金融龙头。",
            "kind": "preset_pool",
            "codes": [
                "00005", "02318", "01299", "03988", "01398", "02388", "00388", "02628", "03328", "02318",
                "02888", "00939", "03968", "03618", "02328", "06030", "06837", "01766", "01111", "02601",
            ],
        },
        {
            "key": "hk_consumer",
            "label": "港股消费品牌",
            "description": "聚焦消费、连锁零售、体育用品和平台型消费品牌。",
            "kind": "preset_pool",
            "codes": [
                "02319", "02020", "06862", "09987", "01929", "09992", "06690", "09868", "09626", "02269",
                "01579", "06169", "01044", "09991", "02150", "09696", "02162", "09896", "06618", "09999",
            ],
        },
        {
            "key": "custom_pool",
            "label": "自定义股票池",
            "description": "手动输入港股代码，适合和你的自选池保持一致。",
            "kind": "custom_pool",
        },
    ],
    "us": [
        {
            "key": "us_board_industry_dynamic",
            "label": "美股行业板块（自定义）",
            "description": "从后端维护的美股行业池中选择一个行业，并按该行业代表成分股扫描。",
            "kind": "board_dynamic",
            "board_type": "industry",
        },
        {
            "key": "us_big_tech",
            "label": "美股科技龙头",
            "description": "聚焦美股大盘科技与平台公司，适合看主线趋势。",
            "kind": "preset_pool",
            "codes": [
                "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "NFLX", "TSLA", "ORCL", "CRM",
                "ADBE", "INTU", "CSCO", "IBM", "QCOM", "AMD", "AVGO", "UBER", "SHOP", "NOW",
            ],
        },
        {
            "key": "us_semiconductor",
            "label": "美股半导体",
            "description": "聚焦 AI 算力、晶圆代工、设备和设计龙头。",
            "kind": "preset_pool",
            "codes": [
                "NVDA", "AMD", "AVGO", "TSM", "MU", "QCOM", "INTC", "AMAT", "LRCX", "KLAC",
                "ASML", "MRVL", "ADI", "TXN", "MCHP", "ON", "ARM", "SMCI", "TER", "NXPI",
            ],
        },
        {
            "key": "us_finance",
            "label": "美股金融权重",
            "description": "聚焦银行、券商、交易所和资管龙头。",
            "kind": "preset_pool",
            "codes": [
                "JPM", "BAC", "GS", "MS", "C", "WFC", "BLK", "SCHW", "AXP", "KKR",
                "BX", "SPGI", "ICE", "CME", "CB", "AIG", "PGR", "MMC", "PNC", "TROW",
            ],
        },
        {
            "key": "us_consumer",
            "label": "美股消费零售",
            "description": "聚焦零售、餐饮、旅游和可选消费龙头。",
            "kind": "preset_pool",
            "codes": [
                "AMZN", "COST", "WMT", "HD", "SBUX", "MCD", "NKE", "TGT", "LOW", "BKNG",
                "DIS", "RCL", "MAR", "LULU", "TJX", "CMG", "YUM", "ROST", "EBAY", "ETSY",
            ],
        },
        {
            "key": "custom_pool",
            "label": "自定义股票池",
            "description": "手动输入美股代码，适合扫描自己的观察名单。",
            "kind": "custom_pool",
        },
    ],
}


STOCK_SCREENER_DYNAMIC_BOARD_CONFIG: Dict[str, Dict[str, List[BoardConfig]]] = {
    "hk": {
        "industry": [
            {
                "board_name": "科技互联网",
                "label": "科技互联网",
                "description": "港股平台互联网、软件服务、消费互联网与部分硬科技龙头。",
                "tiers": [
                    {"key": "leaders", "label": "龙头", "codes": ["00700", "09988", "03690", "09618"]},
                    {"key": "core", "label": "中军", "codes": ["09888", "01024", "06618", "09999"]},
                    {"key": "momentum", "label": "弹性", "codes": ["09868", "09626", "09961", "03888"]},
                ],
            },
            {
                "board_name": "半导体",
                "label": "半导体",
                "description": "港股晶圆代工、封测、设备与上游零部件代表公司。",
                "tiers": [
                    {"key": "leaders", "label": "龙头", "codes": ["00981", "01347", "00381", "00995", "02878"]},
                    {"key": "core", "label": "中军", "codes": ["01478", "00489", "02018", "02382"]},
                    {"key": "momentum", "label": "弹性", "codes": ["00469", "00931", "00522", "00480"]},
                ],
            },
            {
                "board_name": "新能源车",
                "label": "新能源车",
                "description": "港股整车、电池、材料与智能驾驶产业链代表公司。",
                "tiers": [
                    {"key": "leaders", "label": "龙头", "codes": ["01211", "09868", "02015", "02238"]},
                    {"key": "core", "label": "中军", "codes": ["00992", "01772", "00285"]},
                    {"key": "momentum", "label": "弹性", "codes": ["03931", "01787", "03800"]},
                ],
            },
            {
                "board_name": "消费零售",
                "label": "消费零售",
                "description": "港股消费品牌、餐饮连锁、运动服饰与零售平台代表公司。",
                "tiers": [
                    {"key": "leaders", "label": "龙头", "codes": ["02319", "02020", "06862", "01929"]},
                    {"key": "core", "label": "中军", "codes": ["09992", "06110", "09991", "02150"]},
                    {"key": "momentum", "label": "弹性", "codes": ["01579", "09987", "06169", "09896"]},
                ],
            },
            {
                "board_name": "金融",
                "label": "金融",
                "description": "港股银行、保险、交易所、券商与综合金融龙头。",
                "tiers": [
                    {"key": "leaders", "label": "龙头", "codes": ["00005", "02318", "01299", "00388"]},
                    {"key": "core", "label": "中军", "codes": ["03988", "01398", "02388", "06030"]},
                    {"key": "momentum", "label": "弹性", "codes": ["06837", "02628", "01111", "02601"]},
                ],
            },
            {
                "board_name": "医药医疗",
                "label": "医药医疗",
                "description": "港股创新药、CXO、医疗器械和互联网医疗代表公司。",
                "tiers": [
                    {"key": "leaders", "label": "龙头", "codes": ["01093", "01177", "02162", "02269"]},
                    {"key": "core", "label": "中军", "codes": ["06606", "09926", "09696", "01801"]},
                    {"key": "momentum", "label": "弹性", "codes": ["06185", "02273", "01513", "01099"]},
                ],
            },
            {
                "board_name": "能源公用",
                "label": "能源公用",
                "description": "港股油气、煤炭、电力与公用事业权重股。",
                "tiers": [
                    {"key": "leaders", "label": "龙头", "codes": ["00857", "00386", "00883", "01088"]},
                    {"key": "core", "label": "中军", "codes": ["00902", "00836", "00956"]},
                    {"key": "momentum", "label": "弹性", "codes": ["00941", "00002", "02638"]},
                ],
            },
            {
                "board_name": "地产基建",
                "label": "地产基建",
                "description": "港股地产开发、物业、建筑央企与基建链代表公司。",
                "tiers": [
                    {"key": "leaders", "label": "龙头", "codes": ["01109", "00688", "01113", "00960"]},
                    {"key": "core", "label": "中军", "codes": ["01800", "01186", "03311", "03383"]},
                    {"key": "momentum", "label": "弹性", "codes": ["00123", "01972", "00604", "00914"]},
                ],
            },
            {
                "board_name": "航运物流",
                "label": "航运物流",
                "description": "港股集运、港口、航运服务与综合物流代表公司。",
                "tiers": [
                    {"key": "leaders", "label": "龙头", "codes": ["01919", "00316", "01199", "01308"]},
                    {"key": "core", "label": "中军", "codes": ["02343", "02866", "01446", "01382"]},
                    {"key": "momentum", "label": "弹性", "codes": ["00598", "00517", "02198", "06198"]},
                ],
            },
            {
                "board_name": "博彩旅游",
                "label": "博彩旅游",
                "description": "港股博彩、酒店、在线旅游与出行服务代表公司。",
                "tiers": [
                    {"key": "leaders", "label": "龙头", "codes": ["00027", "01928", "02282", "01128"]},
                    {"key": "core", "label": "中军", "codes": ["00200", "09961", "00069", "00780"]},
                    {"key": "momentum", "label": "弹性", "codes": ["00880", "01691", "02799", "06969"]},
                ],
            },
            {
                "board_name": "通信设备与运营",
                "label": "通信设备与运营",
                "description": "港股运营商、通信设备、光通信与网络服务代表公司。",
                "tiers": [
                    {"key": "leaders", "label": "龙头", "codes": ["00941", "00728", "00762", "00763"]},
                    {"key": "core", "label": "中军", "codes": ["00552", "02342", "06869", "01415"]},
                    {"key": "momentum", "label": "弹性", "codes": ["01310", "00354", "00497", "02500"]},
                ],
            },
        ],
    },
    "us": {
        "industry": [
            {
                "board_name": "科技平台",
                "label": "科技平台",
                "description": "美股大型平台、云计算与企业软件龙头。",
                "tiers": [
                    {"key": "leaders", "label": "龙头", "codes": ["AAPL", "MSFT", "GOOGL", "AMZN"]},
                    {"key": "core", "label": "中军", "codes": ["META", "ORCL", "CRM", "ADBE"]},
                    {"key": "momentum", "label": "弹性", "codes": ["NOW", "INTU", "SHOP", "UBER"]},
                ],
            },
            {
                "board_name": "半导体",
                "label": "半导体",
                "description": "美股 AI 算力、晶圆代工、设备与模拟芯片代表公司。",
                "tiers": [
                    {"key": "leaders", "label": "龙头", "codes": ["NVDA", "AMD", "AVGO", "TSM", "ASML"]},
                    {"key": "core", "label": "中军", "codes": ["MU", "QCOM", "INTC", "AMAT", "MRVL"]},
                    {"key": "momentum", "label": "弹性", "codes": ["LRCX", "KLAC", "ADI", "TXN", "MCHP"]},
                ],
            },
            {
                "board_name": "软件安全",
                "label": "软件安全",
                "description": "美股 SaaS、数据库、网络安全与基础软件代表公司。",
                "tiers": [
                    {"key": "leaders", "label": "龙头", "codes": ["PANW", "CRWD", "ZS", "DDOG"]},
                    {"key": "core", "label": "中军", "codes": ["MDB", "SNOW", "NET", "OKTA"]},
                    {"key": "momentum", "label": "弹性", "codes": ["FTNT", "TEAM", "HUBS", "PLTR"]},
                ],
            },
            {
                "board_name": "AI 与算力基础设施",
                "label": "AI 与算力基础设施",
                "description": "美股 AI 服务器、数据中心、电力设备与算力基础设施公司。",
                "tiers": [
                    {"key": "leaders", "label": "龙头", "codes": ["NVDA", "SMCI", "VRT", "ANET"]},
                    {"key": "core", "label": "中军", "codes": ["DELL", "MRVL", "AMD", "AVGO"]},
                    {"key": "momentum", "label": "弹性", "codes": ["EQIX", "DLR", "CEG", "VST"]},
                ],
            },
            {
                "board_name": "金融",
                "label": "金融",
                "description": "美股银行、券商、交易所、支付和另类资管龙头。",
                "tiers": [
                    {"key": "leaders", "label": "龙头", "codes": ["JPM", "BAC", "GS", "MS"]},
                    {"key": "core", "label": "中军", "codes": ["SCHW", "SPGI", "ICE", "CME"]},
                    {"key": "momentum", "label": "弹性", "codes": ["AXP", "KKR", "BX", "BLK"]},
                ],
            },
            {
                "board_name": "消费零售",
                "label": "消费零售",
                "description": "美股零售、餐饮、旅游和品牌消费公司。",
                "tiers": [
                    {"key": "leaders", "label": "龙头", "codes": ["AMZN", "COST", "WMT", "HD"]},
                    {"key": "core", "label": "中军", "codes": ["MCD", "SBUX", "NKE", "BKNG"]},
                    {"key": "momentum", "label": "弹性", "codes": ["LULU", "CMG", "TJX", "ROST"]},
                ],
            },
            {
                "board_name": "医疗健康",
                "label": "医疗健康",
                "description": "美股创新药、医疗器械、健康险与生物科技代表公司。",
                "tiers": [
                    {"key": "leaders", "label": "龙头", "codes": ["LLY", "NVO", "JNJ", "MRK"]},
                    {"key": "core", "label": "中军", "codes": ["ABT", "ISRG", "UNH", "TMO"]},
                    {"key": "momentum", "label": "弹性", "codes": ["DHR", "AMGN", "VRTX", "REGN"]},
                ],
            },
            {
                "board_name": "能源工业",
                "label": "能源工业",
                "description": "美股油气、工业自动化、军工与运输设备代表公司。",
                "tiers": [
                    {"key": "leaders", "label": "龙头", "codes": ["XOM", "CVX", "COP", "CAT"]},
                    {"key": "core", "label": "中军", "codes": ["SLB", "GE", "DE", "RTX"]},
                    {"key": "momentum", "label": "弹性", "codes": ["LMT", "UNP", "ETN", "PH"]},
                ],
            },
            {
                "board_name": "公用事业",
                "label": "公用事业",
                "description": "美股电力、公用事业与独立电力运营商代表公司。",
                "tiers": [
                    {"key": "leaders", "label": "龙头", "codes": ["NEE", "SO", "DUK", "AEP"]},
                    {"key": "core", "label": "中军", "codes": ["SRE", "EXC", "PEG", "XEL"]},
                    {"key": "momentum", "label": "弹性", "codes": ["ED", "EIX", "CEG", "VST"]},
                ],
            },
            {
                "board_name": "REITs",
                "label": "REITs",
                "description": "美股塔类、物流、数据中心、住宅与零售 REIT 代表公司。",
                "tiers": [
                    {"key": "leaders", "label": "龙头", "codes": ["AMT", "PLD", "EQIX", "DLR"]},
                    {"key": "core", "label": "中军", "codes": ["O", "SPG", "WELL", "AVB"]},
                    {"key": "momentum", "label": "弹性", "codes": ["PSA", "VICI", "EQR", "ARE"]},
                ],
            },
            {
                "board_name": "航空航天军工",
                "label": "航空航天军工",
                "description": "美股整机、发动机、航电与军工主承包商代表公司。",
                "tiers": [
                    {"key": "leaders", "label": "龙头", "codes": ["RTX", "LMT", "NOC", "GD"]},
                    {"key": "core", "label": "中军", "codes": ["BA", "LHX", "HWM", "TDG"]},
                    {"key": "momentum", "label": "弹性", "codes": ["HEI", "TXT", "GE", "SPR"]},
                ],
            },
            {
                "board_name": "材料化工",
                "label": "材料化工",
                "description": "美股工业气体、涂料、化工与金属材料代表公司。",
                "tiers": [
                    {"key": "leaders", "label": "龙头", "codes": ["LIN", "APD", "SHW", "ECL"]},
                    {"key": "core", "label": "中军", "codes": ["FCX", "NEM", "NUE", "DD"]},
                    {"key": "momentum", "label": "弹性", "codes": ["CF", "MOS", "MLM", "VMC"]},
                ],
            },
            {
                "board_name": "汽车出行",
                "label": "汽车出行",
                "description": "美股整车、智能驾驶、共享出行与汽车零部件代表公司。",
                "tiers": [
                    {"key": "leaders", "label": "龙头", "codes": ["TSLA", "GM", "F", "UBER"]},
                    {"key": "core", "label": "中军", "codes": ["RIVN", "LYFT", "STLA", "TM"]},
                    {"key": "momentum", "label": "弹性", "codes": ["LCID", "MBLY", "APTV", "HMC"]},
                ],
            },
        ],
    },
}
