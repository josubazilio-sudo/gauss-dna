import { NextResponse } from "next/server";
import { produtos } from "@/lib/db";

export async function GET(_: Request, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const produto = produtos.find((p) => p.slug === slug);
  if (!produto) return NextResponse.json({ erro: "Produto não encontrado" }, { status: 404 });
  return NextResponse.json(produto);
}
