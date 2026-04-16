'use client'

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import type { DailyData } from '@/lib/supabase'

interface Props {
  data: DailyData[]
}

const fmtSum = (n: number) =>
  new Intl.NumberFormat('ru-RU', { notation: 'compact', maximumFractionDigits: 1 }).format(n)

export default function OrdersSumChart({ data }: Props) {
  const formatted = data.map((d) => ({
    ...d,
    label: d.date.slice(5).replace('-', '.'),
  }))

  return (
    <div className="bg-[#111111] rounded-xl p-5 border border-[#222222]">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-4">
        Выручка по дням (₸)
      </p>
      {formatted.length === 0 ? (
        <p className="text-gray-600 text-sm">Нет данных</p>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={formatted} margin={{ top: 4, right: 4, left: -16, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#222222" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fill: '#555', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: '#555', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={fmtSum}
            />
            <Tooltip
              cursor={{ stroke: '#333' }}
              contentStyle={{
                background: '#1a1a1a',
                border: '1px solid #333',
                borderRadius: '8px',
                fontSize: 13,
              }}
              labelStyle={{ color: '#999' }}
              itemStyle={{ color: '#6ee7b7' }}
              formatter={(value: number) => [
                new Intl.NumberFormat('ru-RU').format(value) + ' ₸',
                'сумма',
              ]}
            />
            <Line
              type="monotone"
              dataKey="sum"
              stroke="#22c55e"
              strokeWidth={2}
              dot={{ fill: '#22c55e', r: 3 }}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
