import React, { useEffect, useRef } from "react";
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Image,
  ViewStyle,
  ListRenderItemInfo,
} from "react-native";

import { Images } from '../theme/Assets';

import {LiveMessage, MessageType} from "../context/VoiceClientContext";


interface ChatViewProps {
  messages: LiveMessage[];
}

const MessageView: React.FC<{ message: LiveMessage }> = ({ message }) => {
  return (
    <View style={[styles.messageContainer, messagePadding(message.type)]}>
      {message.type === "bot" && (
        <Image
          source={Images.dailyBot}
          style={styles.botIcon}
        />
      )}
      <View
        style={[
          styles.messageBubble,
          { backgroundColor: messageBackgroundColor(message.type) },
        ]}
      >
        <Text style={[styles.messageText, { color: "#fff" }]}>{message.content}</Text>
      </View>
    </View>
  );
};

export const ChatView: React.FC<ChatViewProps> = ({ messages }) => {
  const flatListRef = useRef<FlatList<LiveMessage>>(null);

  // Auto-scroll to the bottom when messages change
  useEffect(() => {
    if (messages.length > 0) {
      flatListRef.current?.scrollToEnd({ animated: true });
    }
  }, [messages]);

  const renderItem = (info: ListRenderItemInfo<LiveMessage>) => {
    const alignment: ViewStyle = {
      alignItems: messageAlignment(info.item.type),
      width: "100%",
    };
    return (
      <View style={alignment}>
        <MessageView message={info.item} />
      </View>
    );
  };

  return (
    <View style={styles.container}>
      <FlatList
        data={messages}
        renderItem={renderItem}
        keyExtractor={item => item.id}
        ref={flatListRef}
        contentContainerStyle={styles.list}
        onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: true })}
      />
    </View>
  );
};

// Helper functions
function messageAlignment(type: MessageType): ViewStyle["alignItems"] {
  switch (type) {
    case "bot":
      return "flex-start";
    case "user":
      return "flex-end";
    case "system":
      return "center";
  }
}

function messageBackgroundColor(type: MessageType): string {
  switch (type) {
    case "bot":
      return "#101010";
    case "user":
      return "#606060";
    case "system":
      return "rgba(52, 120, 246, 0.6)";
  }
}

function messagePadding(type: MessageType): ViewStyle {
  switch (type) {
    case "bot":
      return { marginRight: 40, marginVertical: 4 };
    case "user":
      return { marginLeft: 40, marginVertical: 4 };
    case "system":
      return { marginVertical: 4 };
  }
}

// Styles
const styles = StyleSheet.create({
  container: {
    flex: 1,
    paddingBottom: 10,
    backgroundColor: "transparent",
  },
  list: {
    flexGrow: 1,
    justifyContent: "flex-end",
    paddingHorizontal: 10,
  },
  messageContainer: {
    flexDirection: "row",
    alignItems: "center",
    maxWidth: "90%",
  },
  botIcon: {
    width: 24,
    height: 24,
    marginRight: 6,
  },
  messageBubble: {
    borderRadius: 16,
    paddingVertical: 9,
    paddingHorizontal: 13,
    borderWidth: 1,
    borderColor: "rgba(128,128,128,0.5)",
  },
  messageText: {
    fontSize: 16,
  },
});

export default ChatView;