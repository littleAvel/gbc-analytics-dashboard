import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

export const supabase = createClient(supabaseUrl, supabaseAnonKey)

export interface Order {
  id: number
  retailcrm_id: string
  first_name: string | null
  last_name: string | null
  total_sum: number
  status: string | null
  city: string | null
  created_at: string
}

export interface DailyData {
  date: string   // "YYYY-MM-DD"
  count: number
  sum: number
}
