import { View, Text, FlatList, TouchableOpacity } from "react-native";

const posts = [
  { id: 1, autor: "Confeitaria", img: "🎂", texto: "Bolo de aniversário que fizemos hoje!", curtidas: 24 },
  { id: 2, autor: "Confeitaria", img: "🧁", texto: "Nossos novos cupcakes de chocolate belga 🍫", curtidas: 31 },
  { id: 3, autor: "Confeitaria", img: "🍰", texto: "Torta de morango da semana, quem quer?", curtidas: 18 },
];

export default function Social() {
  return (
    <View className="flex-1 bg-amber-50 px-4 pt-4">
      <FlatList
        data={posts}
        contentContainerStyle={{ gap: 16, paddingBottom: 20 }}
        renderItem={({ item }) => (
          <View className="bg-white rounded-2xl p-4 shadow-sm">
            <View className="flex-row items-center gap-3 mb-2">
              <View className="w-10 h-10 bg-pink-100 rounded-full items-center justify-center">
                <Text className="text-xl">👩‍🍳</Text>
              </View>
              <Text className="font-semibold">{item.autor}</Text>
            </View>
            <Text className="text-5xl text-center py-4">{item.img}</Text>
            <Text className="mb-2">{item.texto}</Text>
            <View className="flex-row gap-4">
              <TouchableOpacity className="flex-row items-center gap-1">
                <Text>❤️ {item.curtidas}</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}
      />
    </View>
  );
}
