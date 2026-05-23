// ============================================================
// 004_health_check.ts
// Life System — Supabase Edge Function
// Daily health-check: reads player_state, returns status JSON
// Also keeps the Supabase project alive (prevents spin-down)
// ============================================================

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

Deno.serve(async (_req: Request): Promise<Response> => {
  try {
    const supabaseUrl = Deno.env.get("SUPABASE_URL");
    const supabaseKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");

    if (!supabaseUrl || !supabaseKey) {
      return new Response(
        JSON.stringify({
          status: "error",
          message: "Missing SUPABASE_URL or SUPABASE_SERVICE_KEY env vars",
        }),
        { status: 500, headers: { "Content-Type": "application/json" } },
      );
    }

    const supabase = createClient(supabaseUrl, supabaseKey);

    const { data, error } = await supabase
      .from("player_state")
      .select("mh_score, last_updated")
      .eq("id", 1)
      .single();

    if (error) {
      return new Response(
        JSON.stringify({
          status: "error",
          message: error.message,
        }),
        { status: 500, headers: { "Content-Type": "application/json" } },
      );
    }

    if (!data) {
      return new Response(
        JSON.stringify({
          status: "error",
          message: "player_state singleton row not found (id = 1)",
        }),
        { status: 404, headers: { "Content-Type": "application/json" } },
      );
    }

    return new Response(
      JSON.stringify({
        status: "ok",
        mh_score: data.mh_score,
        last_updated: data.last_updated,
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return new Response(
      JSON.stringify({
        status: "error",
        message,
      }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }
});
