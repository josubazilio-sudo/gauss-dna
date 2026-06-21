import { View, Text, FlatList, TouchableOpacity } from "react-native";

const produtos = [
  { id: 1, nome: "Bolo de Chocolate", preco: 89.90, img: "🍫", categoria: "Bolos" },
  { id: 2, nome: "Bolo de Morango", preco: 94.90, img: "🍓", categoria: "Bolos" },
  { id: 3, nome: "Bolo de Cenoura", preco: 79.90, img: "🥕", categoria: "Bolos" },
  { id: 4, nome: "Bolo de Limão", preco: 84.90, img: "🍋", categoria: "Bolos" },
  { id: 5, nome: "Brigadeiro (unid)", preco: 3.50, img: "🍫", categoria: "Doces" },
  { id: 6, nome: "Cupcake", preco: 8.90, img: "🧁", categoria: "Doces" },
  { id: 7, nome: "Torta de Morango", preco: 69.90, img: "🍰", categoria: "Tortas" },
  { id: 8, nome: "Torta de Limão", preco: 64.90, img: "🍋", categoria: "Tortas" },
];

export default function Catalogo() {
  return (
    <View className="flex-1 bg-amber-50 px-4 pt-4">
      <FlatList
        data={produtos}
        numColumns={2}
        columnWrapperStyle={{ gap: 12 }}
        contentContainerStyle={{ gap: 12, paddingBottom: 20 }}
        renderItem={({ item }) => (
          <View className="flex-1 bg-white rounded-2xl p-4 shadow-sm">
            <Text className="text-4xl text-center mb-2">{item.img}</Text>
            <Text className="text-xs bg-pink-100 text-pink-700 px-2 py-1 rounded-full self-start">
              {item.categoria}
            </Text>
            <Text className="font-semibold mt-2 text-base">{item.nome}</Text>
            <Text className="text-pink-600 font-bold text-lg">R$ {item.preco.toFixed(2)}</Text>
            <TouchableOpacity className="mt-2 bg-pink-600 py-2 rounded-full">
              <Text className="text-white text-sm font-semibold text-center">Adicionar</Text>
            </TouchableOpacity>
          </View>
        )}
      />
    </View>
  );
}
