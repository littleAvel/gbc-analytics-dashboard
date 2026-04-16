'use client'

import {
  BarChart,
  Bar,
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

export default function OrdersBarChart({ data }: Props) {
  const formatted = data.map((d) => ({
    ...d,
    label: d.date.slice(5).replace('-', '.'), // "01.15"
  }))

  return (
    <div className="bg-[#111111] rounded-xl p-5 border border-[#222222]">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-4">
        Заказов по дням
      </p>
      {formatted.length === 0 ? (
        <p className="text-gray-600 text-sm">Нет данных</p>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={formatted} margin={{ top: 4, right: 4, left: -16, bottom: 0 }}>
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
              allowDecimals={false}
            />
            <Tooltip
              cursor={{ fill: '#ffffff08' }}
              contentStyle={{
                background: '#1a1a1a',
                border: '1px solid #333',
                borderRadius: '8px',
                fontSize: 13,
              }}
              labelStyle={{ color: '#999' }}
              itemStyle={{ color: '#a5b4fc' }}
              formatter={(value: number) => [value, 'заказов']}
            />
            <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
