import apiClient from './index';

export type ExtractItem = {
  code?: string | null;
  name?: string | null;
  confidence: string;
};

export type ExtractFromImageResponse = {
  codes: string[];
  items?: ExtractItem[];
  rawText?: string;
};

export type BrokerRecommendationItem = {
  rank: number;
  code: string;
  tsCode: string;
  name?: string | null;
  market: 'cn' | 'hk' | 'us' | string;
  brokerCount: number;
  brokers: string[];
};

export type BrokerRecommendationBrokerPick = {
  rank: number;
  code: string;
  tsCode: string;
  name?: string | null;
  market: 'cn' | 'hk' | 'us' | string;
  brokerCount: number;
};

export type BrokerRecommendationBrokerItem = {
  rank: number;
  broker: string;
  pickCount: number;
  picks: BrokerRecommendationBrokerPick[];
};

export type BrokerRecommendationResponse = {
  month?: string | null;
  updatedAt?: string | null;
  availableMonths: string[];
  brokerTotal: number;
  totalPicks: number;
  items: BrokerRecommendationItem[];
  brokers: BrokerRecommendationBrokerItem[];
};

export const stocksApi = {
  async extractFromImage(file: File): Promise<ExtractFromImageResponse> {
    const formData = new FormData();
    formData.append('file', file);

    const headers: { [key: string]: string | undefined } = { 'Content-Type': undefined };
    const response = await apiClient.post(
      '/api/v1/stocks/extract-from-image',
      formData,
      {
        headers,
        timeout: 60000, // Vision API can be slow; 60s
      },
    );

    const data = response.data as { codes?: string[]; items?: ExtractItem[]; raw_text?: string };
    return {
      codes: data.codes ?? [],
      items: data.items,
      rawText: data.raw_text,
    };
  },

  async parseImport(file?: File, text?: string): Promise<ExtractFromImageResponse> {
    if (file) {
      const formData = new FormData();
      formData.append('file', file);
      const headers: { [key: string]: string | undefined } = { 'Content-Type': undefined };
      const response = await apiClient.post('/api/v1/stocks/parse-import', formData, { headers });
      const data = response.data as { codes?: string[]; items?: ExtractItem[] };
      return { codes: data.codes ?? [], items: data.items };
    }
    if (text) {
      const response = await apiClient.post('/api/v1/stocks/parse-import', { text });
      const data = response.data as { codes?: string[]; items?: ExtractItem[] };
      return { codes: data.codes ?? [], items: data.items };
    }
    throw new Error('请提供文件或粘贴文本');
  },

  async getBrokerRecommendations(month?: string, limit = 12): Promise<BrokerRecommendationResponse> {
    const response = await apiClient.get('/api/v1/stocks/broker-recommendations', {
      params: {
        month: month || undefined,
        limit,
      },
    });
    const data = response.data as {
      month?: string | null;
      updated_at?: string | null;
      available_months?: string[];
      broker_total?: number;
      total_picks?: number;
      items?: Array<{
        rank: number;
        code: string;
        ts_code: string;
        name?: string | null;
        market: 'cn' | 'hk' | 'us' | string;
        broker_count: number;
        brokers?: string[];
      }>;
      brokers?: Array<{
        rank: number;
        broker: string;
        pick_count: number;
        picks?: Array<{
          rank: number;
          code: string;
          ts_code: string;
          name?: string | null;
          market: 'cn' | 'hk' | 'us' | string;
          broker_count: number;
        }>;
      }>;
    };
    return {
      month: data.month,
      updatedAt: data.updated_at,
      availableMonths: data.available_months ?? [],
      brokerTotal: data.broker_total ?? 0,
      totalPicks: data.total_picks ?? 0,
      items: (data.items ?? []).map((item) => ({
        rank: item.rank,
        code: item.code,
        tsCode: item.ts_code,
        name: item.name,
        market: item.market,
        brokerCount: item.broker_count,
        brokers: item.brokers ?? [],
      })),
      brokers: (data.brokers ?? []).map((item) => ({
        rank: item.rank,
        broker: item.broker,
        pickCount: item.pick_count,
        picks: (item.picks ?? []).map((pick) => ({
          rank: pick.rank,
          code: pick.code,
          tsCode: pick.ts_code,
          name: pick.name,
          market: pick.market,
          brokerCount: pick.broker_count,
        })),
      })),
    };
  },

  async refreshBrokerRecommendations(month?: string, historyMonths = 3, top = 50, limit = 12): Promise<BrokerRecommendationResponse> {
    const response = await apiClient.post('/api/v1/stocks/broker-recommendations/refresh', null, {
      params: {
        month: month || undefined,
        history_months: historyMonths,
        top,
        limit,
      },
    });
    const data = response.data as {
      month?: string | null;
      updated_at?: string | null;
      available_months?: string[];
      broker_total?: number;
      total_picks?: number;
      items?: Array<{
        rank: number;
        code: string;
        ts_code: string;
        name?: string | null;
        market: 'cn' | 'hk' | 'us' | string;
        broker_count: number;
        brokers?: string[];
      }>;
      brokers?: Array<{
        rank: number;
        broker: string;
        pick_count: number;
        picks?: Array<{
          rank: number;
          code: string;
          ts_code: string;
          name?: string | null;
          market: 'cn' | 'hk' | 'us' | string;
          broker_count: number;
        }>;
      }>;
    };
    return {
      month: data.month,
      updatedAt: data.updated_at,
      availableMonths: data.available_months ?? [],
      brokerTotal: data.broker_total ?? 0,
      totalPicks: data.total_picks ?? 0,
      items: (data.items ?? []).map((item) => ({
        rank: item.rank,
        code: item.code,
        tsCode: item.ts_code,
        name: item.name,
        market: item.market,
        brokerCount: item.broker_count,
        brokers: item.brokers ?? [],
      })),
      brokers: (data.brokers ?? []).map((item) => ({
        rank: item.rank,
        broker: item.broker,
        pickCount: item.pick_count,
        picks: (item.picks ?? []).map((pick) => ({
          rank: pick.rank,
          code: pick.code,
          tsCode: pick.ts_code,
          name: pick.name,
          market: pick.market,
          brokerCount: pick.broker_count,
        })),
      })),
    };
  },
};
