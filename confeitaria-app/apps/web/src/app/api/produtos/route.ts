import { NextResponse } from "next/server";
import { produtos } from "@/lib/db";

export async function GET() {
  return NextResponse.json(produtos);
}
