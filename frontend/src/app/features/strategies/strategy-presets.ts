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
    name: 'Fortress Breakout (S/R × quality × volume)',
    description: 'Major resistance only breaks for real when real money pushes through it. '
      + 'Entry: a financially sound company (ROE > 12%, debt/equity < 1.5) closes above '
      + 'its confirmed swing resistance on above-average volume (> 1× the 20-day volume '
      + 'average — the conviction filter that separates breakouts from head-fakes). '
      + 'Broken resistance becomes support: exit only if price falls back through swing '
      + 'support, with a 2.5× ATR trailing stop as the safety net.',
    definition: {
      entry: [
        { left: 'roe_pct', op: 'gt', right: 12 },                    // sound business
        { left: 'debt_to_equity', op: 'lt', right: 1.5 },            // survivable balance sheet
        { left: 'close', op: 'crosses_above', right: 'resistance' }, // major level breaks
        { left: 'volume', op: 'gt', right: 'vol_sma_20' },           // with real participation
      ],
      exit: [{ left: 'close', op: 'crosses_below', right: 'support' }],
      stop_loss_pct: null,
      take_profit_pct: null,
      max_holding_days: null,
      atr_stop_mult: 2.5,
      atr_trail: true,
    },
  },
  {
    name: 'Fortress Range (buy support, sell resistance)',
    description: 'The classic S/R range trade, quality-filtered: when a sound company '
      + '(ROE > 12%) reclaims its swing support on above-average volume — buyers '
      + 'defending the level with size — buy the bounce. Sell when price reaches swing '
      + 'resistance (the other wall of the range). A 2× ATR stop guards against the '
      + 'reclaim failing, and 45 bars time-boxes dead ranges.',
    definition: {
      entry: [
        { left: 'roe_pct', op: 'gt', right: 12 },
        { left: 'close', op: 'crosses_above', right: 'support' },    // the level held
        { left: 'volume', op: 'gt', right: 'vol_sma_20' },           // defended with size
      ],
      exit: [{ left: 'close', op: 'gte', right: 'resistance' }],     // sell into the wall
      stop_loss_pct: null,
      take_profit_pct: null,
      max_holding_days: 45,
      atr_stop_mult: 2,
      atr_trail: false,
    },
  },
  {
    name: 'Momentum Leader (RS + trend + breakout)',
    description: 'The Momentum Engine as a strategy: only top-quartile relative-strength '
      + 'stocks (rs_rank > 75), in a confirmed uptrend (close > SMA-200, SMA-50 > SMA-200), '
      + 'entered on a new-highs breakout above resistance. '
      + 'ATR trailing stop rides the winner; RS decay below 50 is the exit tell. '
      + 'rs_rank is computed point-in-time — this backtest has no lookahead.',
    definition: {
      entry: [
        { left: 'rs_rank', op: 'gt', right: 75 },              // a leader, not a laggard
        { left: 'close', op: 'gt', right: 'sma_200' },         // long-term uptrend
        { left: 'sma_50', op: 'gt', right: 'sma_200' },        // trend structure aligned
        { left: 'close', op: 'crosses_above', right: 'resistance' },  // the trigger
      ],
      exit: [
        { left: 'rs_rank', op: 'lt', right: 50 },              // leadership lost = thesis dead
      ],
      stop_loss_pct: null,
      take_profit_pct: null,
      max_holding_days: null,
      atr_stop_mult: 3,
      atr_trail: true,                                          // ratchet up, never down
    },
  },
  {
    name: 'Momentum Pullback (buy leaders on weakness)',
    description: 'Strong stocks (rs_rank > 80) in uptrends, bought on a short-term RSI dip '
      + 'below 45 instead of chased at highs — the lower-risk momentum entry. Exits when '
      + 'the bounce matures (RSI > 70) or after 30 bars, with a 2.5× ATR safety stop.',
    definition: {
      entry: [
        { left: 'rs_rank', op: 'gt', right: 80 },
        { left: 'close', op: 'gt', right: 'sma_200' },
        { left: 'sma_50', op: 'gt', right: 'sma_200' },
        { left: 'rsi_14', op: 'lt', right: 45 },
      ],
      exit: [{ left: 'rsi_14', op: 'gt', right: 70 }],
      stop_loss_pct: null,
      take_profit_pct: null,
      max_holding_days: 30,
      atr_stop_mult: 2.5,
      atr_trail: false,
    },
  },
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
    name: 'Intraday 15m: EMA momentum burst',
    description: 'Run with the 15m timeframe. Fast EMA-9 crosses above EMA-21 with RSI '
      + 'confirming (> 55) — a momentum burst entry. Exits on the reverse cross or after '
      + '25 bars (one session), guarded by a tight 1.5× ATR stop. Sync intraday data first; '
      + 'Yahoo only keeps ~60 days, so treat the backtest as a sketch, not proof.',
    definition: {
      entry: [
        { left: 'ema_9', op: 'crosses_above', right: 'ema_21' },
        { left: 'rsi_14', op: 'gt', right: 55 },
      ],
      exit: [{ left: 'ema_9', op: 'crosses_below', right: 'ema_21' }],
      stop_loss_pct: null,
      take_profit_pct: null,
      max_holding_days: 25,               // bars on the 15m timeframe ≈ one session
      atr_stop_mult: 1.5,
      atr_trail: true,
    },
  },
  {
    name: 'Intraday 15m: VWAP-style band fade',
    description: 'Run with the 15m timeframe. Mean-reversion scalp: price stretched below '
      + 'the lower Bollinger band snaps back toward the 20-bar mean (a VWAP-like anchor '
      + 'on 15m bars). Time-boxed to 12 bars (~3 hours) with a 1.2× ATR stop — intraday '
      + 'mean reversion must be fast or wrong.',
    definition: {
      entry: [
        { left: 'close', op: 'lt', right: 'bb_lower' },
        { left: 'rsi_14', op: 'lt', right: 30 },
      ],
      exit: [{ left: 'close', op: 'crosses_above', right: 'bb_mid' }],
      stop_loss_pct: null,
      take_profit_pct: null,
      max_holding_days: 12,               // bars ≈ 3 hours on 15m
      atr_stop_mult: 1.2,
      atr_trail: false,
    },
  },
  {
    name: 'Turtle Breakout (Donchian style)',
    description: 'The famous Turtle Traders system, adapted: buy the breakout above the '
      + 'last confirmed swing high, exit on a close below swing support, risk managed by '
      + 'the classic 2× ATR stop. Pure trend-following — expect many small losses and a '
      + 'few very large winners; judge it on expectancy, not win rate.',
    definition: {
      entry: [
        { left: 'close', op: 'crosses_above', right: 'resistance' },
      ],
      exit: [{ left: 'close', op: 'crosses_below', right: 'support' }],
      stop_loss_pct: null,
      take_profit_pct: null,
      max_holding_days: null,
      atr_stop_mult: 2,
      atr_trail: false,
    },
  },
  {
    name: 'MACD Momentum Cross',
    description: 'Gerald Appel\'s classic: MACD line crosses above its signal line, '
      + 'filtered to long-term uptrends only (close > SMA-200) to avoid counter-trend '
      + 'whipsaws. Exit on the reverse cross.',
    definition: {
      entry: [
        { left: 'macd', op: 'crosses_above', right: 'macd_signal' },
        { left: 'close', op: 'gt', right: 'sma_200' },
      ],
      exit: [{ left: 'macd', op: 'crosses_below', right: 'macd_signal' }],
      stop_loss_pct: 7,
      take_profit_pct: null,
      max_holding_days: null,
    },
  },
  {
    name: 'Connors RSI-2 (mean reversion)',
    description: 'Larry Connors\' famous short-term dip-buy: in a long-term uptrend '
      + '(close > SMA-200), buy an extreme 2-period RSI washout (< 10), exit when price '
      + 'recovers its 5-day average. High win rate, small wins — the anti-Turtle. '
      + 'Works best on liquid large caps.',
    definition: {
      entry: [
        { left: 'close', op: 'gt', right: 'sma_200' },
        { left: 'rsi_2', op: 'lt', right: 10 },
      ],
      exit: [{ left: 'close', op: 'crosses_above', right: 'sma_5' }],
      stop_loss_pct: 5,
      take_profit_pct: null,
      max_holding_days: 10,
    },
  },
  {
    name: 'Bollinger Snapback',
    description: 'John Bollinger\'s bands as a mean-reversion tool: buy a close below '
      + 'the lower band inside an uptrend, exit at the middle band (the 20-day mean). '
      + 'Time-boxed to 15 bars so dead trades don\'t linger.',
    definition: {
      entry: [
        { left: 'close', op: 'lt', right: 'bb_lower' },
        { left: 'close', op: 'gt', right: 'sma_200' },
      ],
      exit: [{ left: 'close', op: 'crosses_above', right: 'bb_mid' }],
      stop_loss_pct: 6,
      take_profit_pct: null,
      max_holding_days: 15,
    },
  },
  {
    name: 'Minervini Trend Template (lite)',
    description: 'Mark Minervini\'s SEPA stage-2 checklist, expressed in rules: price '
      + 'above a rising ladder of moving averages (50 > 150 > 200), top-tier relative '
      + 'strength (rs_rank > 70), entered on a breakout above resistance. Exit when the '
      + '50-day breaks — stage 2 is over.',
    definition: {
      entry: [
        { left: 'close', op: 'gt', right: 'sma_50' },
        { left: 'sma_50', op: 'gt', right: 'sma_150' },
        { left: 'sma_150', op: 'gt', right: 'sma_200' },
        { left: 'rs_rank', op: 'gt', right: 70 },
        { left: 'close', op: 'crosses_above', right: 'resistance' },
      ],
      exit: [{ left: 'close', op: 'crosses_below', right: 'sma_50' }],
      stop_loss_pct: null,
      take_profit_pct: null,
      max_holding_days: null,
      atr_stop_mult: 2.5,
      atr_trail: true,
    },
  },
  {
    name: 'CANSLIM-lite (growth × momentum)',
    description: 'William O\'Neil\'s CANSLIM spirit with the data we store: real earnings '
      + 'growth (> 20%) and revenue growth (> 10%) — the C and A — married to market '
      + 'leadership (rs_rank > 80) and a new-highs breakout. Note: growth filters use '
      + 'today\'s fundamentals (quality screen, not point-in-time).',
    definition: {
      entry: [
        { left: 'earnings_growth_pct', op: 'gt', right: 20 },
        { left: 'revenue_growth_pct', op: 'gt', right: 10 },
        { left: 'rs_rank', op: 'gt', right: 80 },
        { left: 'close', op: 'crosses_above', right: 'resistance' },
      ],
      exit: [{ left: 'close', op: 'crosses_below', right: 'sma_50' }],
      stop_loss_pct: null,
      take_profit_pct: null,
      max_holding_days: null,
      atr_stop_mult: 3,
      atr_trail: true,
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
