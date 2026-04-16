import { supabase } from '@/lib/supabase'
import type { Order, DailyData } from '@/lib/supabase'
import KpiCards from '@/components/KpiCards'
import OrdersBarChart from '@/components/OrdersBarChart'
import OrdersSumChart from '@/components/OrdersSumChart'
import OrdersTable from '@/components/OrdersTable'

export const revalidate = 60

export default async function Page() {
  const { data, error } = await supabase
    .from('orders')
    .select('id, retailcrm_id, first_name, last_name, total_sum, status, city, created_at')
    .order('created_at', { ascending: false })

  if (error) {
    return (
      <main className="min-h-screen bg-[#0a0a0a] flex items-center justify-center">
        <p className="text-red-400 text-sm">Ошибка загрузки данных: {error.message}</p>
      </main>
    )
  }

  const orders: Order[] = data ?? []

  if (orders.length === 0) {
    return (
      <main className="min-h-screen bg-[#0a0a0a] flex items-center justify-center">
        <p className="text-gray-600 text-sm">Нет заказов</p>
      </main>
    )
  }

  // KPI
  const totalOrders = orders.length
  const totalSum = orders.reduce((s, o) => s + (o.total_sum ?? 0), 0)
  const avgSum = totalOrders > 0 ? totalSum / totalOrders : 0

  // Группировка по дням для графиков
  const dailyMap = new Map<string, { count: number; sum: number }>()
  for (const order of orders) {
    const date = order.created_at?.split('T')[0] ?? 'unknown'
    const existing = dailyMap.get(date) ?? { count: 0, sum: 0 }
    existing.count++
    existing.sum += order.total_sum ?? 0
    dailyMap.set(date, existing)
  }
  const dailyData: DailyData[] = Array.from(dailyMap.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, { count, sum }]) => ({ date, count, sum }))

  const recentOrders = orders.slice(0, 10)

  return (
    <main className="min-h-screen bg-[#0a0a0a] text-gray-100">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8 space-y-6">

        {/* Header */}
        <div className="flex items-baseline gap-3">
          <h1 className="text-xl font-semibold tracking-tight text-white">
            GBC Orders Dashboard
          </h1>
          <span className="text-xs text-gray-600">Tomyris</span>
        </div>

        {/* KPI */}
        <KpiCards totalOrders={totalOrders} totalSum={totalSum} avgSum={avgSum} />

        {/* Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <OrdersBarChart data={dailyData} />
          <OrdersSumChart data={dailyData} />
        </div>

        {/* Table */}
        <OrdersTable orders={recentOrders} />

      </div>
    </main>
  )
}
