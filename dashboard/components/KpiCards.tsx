const fmt = (n: number) =>
  new Intl.NumberFormat('ru-RU').format(Math.round(n))

interface Props {
  totalOrders: number
  totalSum: number
  avgSum: number
}

export default function KpiCards({ totalOrders, totalSum, avgSum }: Props) {
  const cards = [
    { label: 'Всего заказов', value: String(totalOrders), unit: '' },
    { label: 'Общая сумма', value: fmt(totalSum), unit: '₸' },
    { label: 'Средний чек', value: fmt(avgSum), unit: '₸' },
  ]

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      {cards.map((card) => (
        <div
          key={card.label}
          className="bg-[#111111] rounded-xl p-5 border border-[#222222]"
        >
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            {card.label}
          </p>
          <p className="mt-2 text-3xl font-bold text-white">
            {card.value}
            {card.unit && (
              <span className="ml-1 text-lg font-normal text-gray-400">
                {card.unit}
              </span>
            )}
          </p>
        </div>
      ))}
    </div>
  )
}
