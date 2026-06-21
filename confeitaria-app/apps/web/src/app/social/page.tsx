import Link from "next/link";

const posts = [
  { id: 1, autor: "Confeitaria", img: "🎂", texto: "Bolo de aniversário que fizemos hoje!",
    curtidas: 24, comentarios: 5, tempo: "2h atrás" },
  { id: 2, autor: "Confeitaria", img: "🧁", texto: "Nossos novos cupcakes de chocolate belga 🍫",
    curtidas: 31, comentarios: 8, tempo: "5h atrás" },
  { id: 3, autor: "Confeitaria", img: "🍰", texto: "Torta de morango da semana, quem quer?",
    curtidas: 18, comentarios: 3, tempo: "1d atrás" },
];

export default function Social() {
  return (
    <main className="min-h-screen">
      <header className="bg-pink-600 text-white p-6 shadow-md">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <Link href="/" className="text-2xl font-bold">Confeitaria</Link>
          <nav className="flex gap-6 text-sm font-medium">
            <Link href="/" className="hover:text-pink-200">Início</Link>
            <Link href="/social" className="text-pink-200">Social</Link>
          </nav>
        </div>
      </header>

      <div className="max-w-2xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold mb-8">Social</h1>

        <div className="space-y-6">
          {posts.map((post) => (
            <div key={post.id} className="bg-white rounded-2xl shadow-sm p-6">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 bg-pink-100 rounded-full flex items-center justify-center text-xl">
                  👩‍🍳
                </div>
                <div>
                  <p className="font-semibold text-sm">{post.autor}</p>
                  <p className="text-xs text-stone-400">{post.tempo}</p>
                </div>
              </div>
              <div className="text-6xl text-center py-4">{post.img}</div>
              <p className="mb-3">{post.texto}</p>
              <div className="flex gap-4 text-sm text-stone-500">
                <button className="flex items-center gap-1 hover:text-pink-600">❤️ {post.curtidas}</button>
                <button className="flex items-center gap-1 hover:text-pink-600">💬 {post.comentarios}</button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
