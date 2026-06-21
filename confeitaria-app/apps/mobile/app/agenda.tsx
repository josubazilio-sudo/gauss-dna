import { View, Text, TextInput, TouchableOpacity, ScrollView } from "react-native";

export default function Agenda() {
  return (
    <ScrollView className="flex-1 bg-amber-50 px-4 pt-4">
      <View className="bg-white rounded-2xl p-6 mb-6">
        <Text className="text-xl font-semibold mb-4">Solicitar Agendamento</Text>
        <TextInput className="border rounded-lg px-3 py-2 mb-3" placeholder="Nome" />
        <TextInput className="border rounded-lg px-3 py-2 mb-3" placeholder="Data desejada" />
        <TextInput className="border rounded-lg px-3 py-2 mb-3" placeholder="Tipo de bolo" />
        <TextInput className="border rounded-lg px-3 py-2 mb-4" placeholder="Observações" multiline numberOfLines={3} />
        <TouchableOpacity className="bg-pink-600 py-3 rounded-full">
          <Text className="text-white font-semibold text-center">Solicitar Agendamento</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}
