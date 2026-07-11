import { StrategyDefinition } from '../../core/models/market-data.models';

export interface StrategyPreset {
  name: string;
  description: string;
  definition: StrategyDefinition;
}

/**
 * Curated long-swing strategies, each expressible in the entry/exit rule DSL.
 * They lean on the trend-following indicators (Ichimoku, SMA, Donchian-style
 * breakouts, support/resistance) that historically capture multi-week swings.
 * These are educational starting points, not trading advice — always backtest.
 */
export const STRATEGY_PRESETS: StrategyPreset[] = [
  {
    name: 'Ichimoku Cloud Breakout',
    description: 'Enter when price closes above the cloud with a bullish Tenkan/Kijun; exit back below the Kijun. Classic long-swing trend rider.',
    definition: {
      entry: [
        { left: 'close', op: 'gt', right: 'ichimoku_cloud_top' },
        { left: 'ichimoku_tenkan', op: 'gt', right: 'ichimoku_kijun' },
      ],
      exit: [{ left: 'close', op: 'crosses_below', right: 'ichimoku_kijun' }],
      stop_loss_pct: 6,
      take_profit_pct: null,
      max_holding_days: null,
    },
  },
  {
    name: 'Ichimoku Tenkan/Kijun Cross',
    description: 'Tenkan crosses above Kijun above the cloud (strong bullish signal); exit on the reverse cross.',
    definition: {
      entry: [
        { left: 'ichimoku_tenkan', op: 'crosses_above', right: 'ichimoku_kijun' },
        { left: 'close', op: 'gt', right: 'ichimoku_cloud_top' },
      ],
      exit: [{ left: 'ichimoku_tenkan', op: 'crosses_below', right: 'ichimoku_kijun' }],
      stop_loss_pct: 7,
      take_profit_pct: null,
      max_holding_days: null,
    },
  },
  {
    name: 'Resistance Breakout',
    description: 'Break above the most recent confirmed swing high (resistance), filtered by a rising 200-day trend. Captures new-highs momentum.',
    definition: {
      entry: [
        { left: 'close', op: 'crosses_above', right: 'resistance' },
        { left: 'close', op: 'gt', right: 'sma_200' },
      ],
      exit: [{ left: 'close', op: 'crosses_below', right: 'support' }],
      stop_loss_pct: 8,
      take_profit_pct: null,
      max_holding_days: null,
    },
  },
  {
    name: 'Golden Cross Trend Rider',
    description: 'SMA-50 crosses above SMA-200 (the golden cross); ride until price closes below SMA-50. Long-horizon trend following.',
    definition: {
      entry: [{ left: 'sma_50', op: 'crosses_above', right: 'sma_200' }],
      exit: [{ left: 'close', op: 'crosses_below', right: 'sma_50' }],
      stop_loss_pct: 10,
      take_profit_pct: null,
      max_holding_days: null,
    },
  },
  {
    name: 'Trend Pullback (buy the dip in an uptrend)',
    description: 'In a confirmed uptrend (price > SMA-200, SMA-50 > SMA-200), buy an RSI pullback below 40; exit when momentum returns hot (RSI > 65).',
    definition: {
      entry: [
        { left: 'close', op: 'gt', right: 'sma_200' },
        { left: 'sma_50', op: 'gt', right: 'sma_200' },
        { left: 'rsi_14', op: 'lt', right: 40 },
      ],
      exit: [{ left: 'rsi_14', op: 'gt', right: 65 }],
      stop_loss_pct: 6,
      take_profit_pct: null,
      max_holding_days: 40,
    },
  },
];
