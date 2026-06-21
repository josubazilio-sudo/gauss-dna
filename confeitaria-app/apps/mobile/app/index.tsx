import { View, Text, TouchableOpacity, ScrollView } from "react-native";
import { StatusBar } from "expo-status-bar";
import { router } from "expo-router";

export default function Home() {
  return (
    <ScrollView className="flex-1 bg-amber-50">
      <StatusBar style="light" />
      <View className="bg-pink-600 p-6 pt-12">
        <Text className="text-white text-3xl font-bold text-center">Confeitaria</Text>
      </View>

      <View className="px-4 py-12 items-center">
        <Text className="text-4xl font-bold text-center text-stone-800 mb-2">
          Bolos artesanais{'\n'}com amor e tradição
        </Text>
        <Text className="text-base text-stone-600 text-center mb-8 px-4">
          Encomende bolos personalizados, doces finos e muito mais. Entrega em toda a cidade.
        </Text>

        <View className="flex-row gap-4">
          <TouchableOpacity
            onPress={() => router.push("/catalogo")}
            className="bg-pink-600 px-8 py-3 rounded-full"
          >
            <Text className="text-white font-semibold">Ver Catálogo</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => router.push("/agenda")}
            className="border-2 border-pink-600 px-8 py-3 rounded-full"
          >
            <Text className="text-pink-600 font-semibold">Agendar Bolo</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View className="bg-white px-4 py-8">
        {[
          { icon: "🎂", title: "Bolos Personalizados", desc: "Do jeito que você sonhou" },
          { icon: "🧁", title: "Doces Finos", desc: "Para todas as ocasiões" },
          { icon: "🚚", title: "Delivery", desc: "Entregamos em sua casa" },
        ].map((item) => (
          <View key={item.title} className="bg-amber-50 p-6 rounded-2xl mb-4 items-center">
            <Text className="text-4xl mb-2">{item.icon}</Text>
            <Text className="text-lg font-semibold">{item.title}</Text>
            <Text className="text-stone-500">{item.desc}</Text>
          </View>
        ))}
      </View>

      <View className="bg-stone-800 p-4 items-center">
        <Text className="text-stone-400 text-sm">&copy; 2026 Confeitaria</Text>
      </View>
    </ScrollView>
  );
}
