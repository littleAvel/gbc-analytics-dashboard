import type { Order } from '@/lib/supabase'

interface Props {
  orders: Order[]
}

const STATUS_STYLES: Record<string, string> = {
  new: 'bg-blue-500/15 text-blue-400',
  assembling: 'bg-yellow-500/15 text-yellow-400',
  delivering: 'bg-orange-500/15 text-orange-400',
  complete: 'bg-green-500/15 text-green-400',
  'cancel-other': 'bg-red-500/15 text-red-400',
}

const STATUS_LABELS: Record<string, string> = {
  new: 'Новый',
  assembling: 'Сборка',
  delivering: 'Доставка',
  complete: 'Выполнен',
  'cancel-other': 'Отмена',
}

const fmt = (n: number) => new Intl.NumberFormat('ru-RU').format(Math.round(n))

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' })
}

export default function OrdersTable({ orders }: Props) {
  return (
    <div className="bg-[#111111] rounded-xl border border-[#222222] overflow-hidden">
      <div className="px-5 py-4 border-b border-[#222222]">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
          Последние заказы
        </p>
      </div>

      {orders.length === 0 ? (
        <p className="px-5 py-8 text-gray-600 text-sm text-center">Нет заказов</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1a1a1a]">
                {['Дата', 'Клиент', 'Сумма', 'Статус', 'Город'].map((h) => (
                  <th
                    key={h}
                    className="px-5 py-3 text-left text-xs text-gray-600 font-medium"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => {
                const statusStyle =
                  STATUS_STYLES[order.status ?? ''] ?? 'bg-gray-500/15 text-gray-400'
                const statusLabel =
                  STATUS_LABELS[order.status ?? ''] ?? order.status ?? '—'
                const client = [order.first_name, order.last_name]
                  .filter(Boolean)
                  .join(' ') || '—'

                return (
                  <tr
                    key={order.id}
                    className="border-b border-[#1a1a1a] last:border-0 hover:bg-white/[0.02] transition-colors"
                  >
                    <td className="px-5 py-3 text-gray-400 whitespace-nowrap">
                      {formatDate(order.created_at)}
                    </td>
                    <td className="px-5 py-3 text-gray-200 whitespace-nowrap">
                      {client}
                    </td>
                    <td className="px-5 py-3 text-white font-medium whitespace-nowrap">
                      {fmt(order.total_sum)} ₸
                    </td>
                    <td className="px-5 py-3">
                      <span
                        className={`inline-block px-2 py-0.5 rounded-md text-xs font-medium ${statusStyle}`}
                      >
                        {statusLabel}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-gray-400">
                      {order.city ?? '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
