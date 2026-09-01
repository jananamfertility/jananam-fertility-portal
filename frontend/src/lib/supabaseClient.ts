import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL as string;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string;

if (!url || !anonKey) {
  // Fails loudly in dev rather than silently breaking auth later.
  // eslint-disable-next-line no-console
  console.error(
    "Missing VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY. Copy frontend/.env.example to " +
      "frontend/.env and fill in your Supabase project's values."
  );
}

export const supabase = createClient(url, anonKey);
