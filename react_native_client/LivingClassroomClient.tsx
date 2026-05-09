/**
 * Living Classroom - React Native WebSocket Client
 * ===============================================
 *
 * Real-time WebSocket client for scene-by-scene streaming from the Living Classroom backend.
 * Cross-platform implementation for React Native (iOS & Android).
 *
 * Architecture: React Native Client ←→ WebSocket ←→ Scene Lifecycle Engine ←→ Multi-Agent System
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  Animated,
  Alert,
  Platform,
  UIManager,
  LayoutAnimation,
} from 'react-native';

// Enable LayoutAnimation on Android
if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

// MARK: - TypeScript Interfaces (matching Python backend exactly)

interface ScenePayload {
  event_type: string;
  session_id: string;
  scene: Scene;
  component_count: number;
}

interface Scene {
  scene_id: string;
  scene_type: SceneType;
  components: Component[];
  priority: number;
  metadata?: SceneMetadata;
}

type SceneType = 'instruction' | 'challenge' | 'celebration' | 'correction' | 'reflection';

interface SceneMetadata {
  estimated_duration_ms?: number;
  difficulty_level?: string;
  concept_tags?: string[];
}

// MARK: - Component System (Server-Driven UI)

interface BaseComponent {
  component_id: string;
  type: ComponentType;
  priority: number;
  delay_ms?: number;
  isVisible?: boolean;
}

type ComponentType =
  | 'TeacherMessage'
  | 'StudentPrompt'
  | 'QuizCard'
  | 'CTAButton'
  | 'Celebration'
  | 'CodeEditor';

interface TeacherMessage extends BaseComponent {
  type: 'TeacherMessage';
  text: string;
  emotion?: string;
  audio_mood?: string;
  concept_tags?: string[];
}

interface QuizCard extends BaseComponent {
  type: 'QuizCard';
  question: string;
  options: QuizOption[];
  concept_id?: string;
}

interface QuizOption {
  id: string;
  label: string;
  is_correct: boolean;
}

interface CTAButton extends BaseComponent {
  type: 'CTAButton';
  label: string;
  action_intent: ActionIntent;
  style?: string;
}

type ActionIntent =
  | 'continue'
  | 'retry'
  | 'hint'
  | 'skip'
  | 'celebrate'
  | 'next_topic';

interface Celebration extends BaseComponent {
  type: 'Celebration';
  message: string;
  celebration_type: string;
  particle_effect?: boolean;
}

type Component = TeacherMessage | QuizCard | CTAButton | Celebration;

// MARK: - WebSocket Client Hook

export const useLivingClassroomClient = (userToken: string, sessionId?: string) => {
  const [isConnected, setIsConnected] = useState(false);
  const [currentScene, setCurrentScene] = useState<Scene | null>(null);
  const [components, setComponents] = useState<Component[]>([]);
  const [connectionState, setConnectionState] = useState<'disconnected' | 'connecting' | 'connected' | 'error'>('disconnected');
  const [lastError, setLastError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const sessionIdRef = useRef(sessionId || generateSessionId());
  const heartbeatRef = useRef<NodeJS.Timeout | null>(null);

  // MARK: - Connection Management

  const connect = useCallback(async () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setConnectionState('connecting');

    const baseURL = 'wss://lyo-production.up.railway.app';
    const wsURL = `${baseURL}/api/v1/classroom/ws/connect`;

    try {
      const websocket = new WebSocket(wsURL, [], {
        headers: {
          'Authorization': `Bearer ${userToken}`,
          'X-Session-ID': sessionIdRef.current,
        }
      });

      websocket.onopen = () => {
        console.log('🎭 Living Classroom WebSocket connected - Session:', sessionIdRef.current);
        setIsConnected(true);
        setConnectionState('connected');
        setLastError(null);
        startHeartbeat();
      };

      websocket.onmessage = (event) => {
        handleMessage(event.data);
      };

      websocket.onerror = (error) => {
        console.error('❌ WebSocket error:', error);
        handleConnectionError('Connection error occurred');
      };

      websocket.onclose = (event) => {
        console.log('👋 WebSocket closed:', event.code, event.reason);
        setIsConnected(false);
        setConnectionState('disconnected');
        stopHeartbeat();

        // Attempt reconnection if not intentional close
        if (event.code !== 1000) {
          setTimeout(() => {
            if (connectionState !== 'disconnected') {
              setConnectionState('connecting');
              connect();
            }
          }, 3000);
        }
      };

      wsRef.current = websocket;

    } catch (error) {
      handleConnectionError(`Failed to connect: ${error}`);
    }
  }, [userToken, connectionState]);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close(1000, 'Client disconnect');
      wsRef.current = null;
    }
    stopHeartbeat();
    setIsConnected(false);
    setConnectionState('disconnected');
  }, []);

  // MARK: - Message Handling

  const handleMessage = useCallback(async (data: string) => {
    try {
      const message = JSON.parse(data);

      // Handle Scene Payload
      if (message.event_type === 'scene_start' && message.scene) {
        await handleScenePayload(message as ScenePayload);
        return;
      }

      // Handle generic messages
      switch (message.event_type) {
        case 'connection_established':
          console.log('✅ Living Classroom connection established');
          break;
        case 'scene_complete':
          console.log('✅ Scene complete');
          break;
        case 'error':
          setLastError(message.message || 'Unknown error');
          console.error('❌ Backend error:', message.message);
          break;
        default:
          console.log('📨 Unknown event:', message.event_type);
      }

    } catch (error) {
      console.error('❌ Failed to process message:', error);
    }
  }, []);

  const handleScenePayload = useCallback(async (payload: ScenePayload) => {
    console.log(`🎬 New scene received: ${payload.scene.scene_type} with ${payload.component_count} components`);

    setCurrentScene(payload.scene);

    // Initialize components with visibility false
    const newComponents = payload.scene.components.map(component => ({
      ...component,
      isVisible: false,
    }));

    setComponents(newComponents);

    // Start progressive rendering
    await progressivelyRenderComponents(newComponents);
  }, []);

  const progressivelyRenderComponents = useCallback(async (components: Component[]) => {
    const sortedComponents = [...components].sort((a, b) => a.priority - b.priority);

    for (let i = 0; i < sortedComponents.length; i++) {
      const component = sortedComponents[i];

      // Apply delay if specified
      if (component.delay_ms && component.delay_ms > 0) {
        await new Promise(resolve => setTimeout(resolve, component.delay_ms));
      }

      // Make component visible with animation
      setComponents(prevComponents =>
        prevComponents.map(comp =>
          comp.component_id === component.component_id
            ? { ...comp, isVisible: true }
            : comp
        )
      );

      // Small delay for animation
      await new Promise(resolve => setTimeout(resolve, 100));
    }
  }, []);

  const handleConnectionError = useCallback((errorMessage: string) => {
    setConnectionState('error');
    setIsConnected(false);
    setLastError(errorMessage);
  }, []);

  // MARK: - User Actions

  const sendUserAction = useCallback(async (intent: ActionIntent, data: Record<string, any> = {}) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket not connected');
    }

    const payload = {
      event_type: 'user_action',
      session_id: sessionIdRef.current,
      action_intent: intent,
      action_data: data,
      timestamp: new Date().toISOString(),
    };

    wsRef.current.send(JSON.stringify(payload));
    console.log('📤 User action sent:', intent);
  }, []);

  const submitQuizAnswer = useCallback(async (questionId: string, selectedOptionId: string, isCorrect: boolean) => {
    await sendUserAction('continue', {
      action_type: 'quiz_submit',
      question_id: questionId,
      selected_option: selectedOptionId,
      is_correct: isCorrect,
    });
  }, [sendUserAction]);

  const requestHint = useCallback(async () => {
    await sendUserAction('hint');
  }, [sendUserAction]);

  const continueLesson = useCallback(async () => {
    await sendUserAction('continue');
  }, [sendUserAction]);

  // MARK: - Heartbeat

  const startHeartbeat = useCallback(() => {
    heartbeatRef.current = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send('ping');
      }
    }, 30000); // 30 seconds
  }, []);

  const stopHeartbeat = useCallback(() => {
    if (heartbeatRef.current) {
      clearInterval(heartbeatRef.current);
      heartbeatRef.current = null;
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return {
    isConnected,
    currentScene,
    components,
    connectionState,
    lastError,
    connect,
    disconnect,
    sendUserAction,
    submitQuizAnswer,
    requestHint,
    continueLesson,
  };
};

// MARK: - React Native Components

interface LivingClassroomViewProps {
  userToken: string;
  sessionId?: string;
}

export const LivingClassroomView: React.FC<LivingClassroomViewProps> = ({
  userToken,
  sessionId,
}) => {
  const client = useLivingClassroomClient(userToken, sessionId);

  useEffect(() => {
    client.connect();
  }, []);

  return (
    <View style={styles.container}>
      {/* Connection Status Header (Glassmorphic) */}
      <View style={styles.statusBar}>
        <View style={styles.statusLeft}>
          <View style={[
            styles.statusIndicator,
            { backgroundColor: client.isConnected ? '#34C759' : '#FF3B30' }
          ]} />
          <Text style={styles.titleText}>Living Classroom</Text>
        </View>
        <View style={styles.statusRight}>
          <Text style={styles.statusText}>
            {client.isConnected ? 'Live' : 'Offline'}
          </Text>
        </View>
      </View>

      {/* Scene Components */}
      <ScrollView 
        style={styles.scrollView} 
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {client.components.map((component) => (
          <ComponentView
            key={component.component_id}
            component={component}
            onQuizSubmit={client.submitQuizAnswer}
            onCTAPress={client.sendUserAction}
          />
        ))}
      </ScrollView>

      {/* Error Display */}
      {client.lastError && (
        <Animated.View style={styles.errorContainer}>
          <Text style={styles.errorText}>{client.lastError}</Text>
        </Animated.View>
      )}
    </View>
  );
};

interface ComponentViewProps {
  component: Component;
  onQuizSubmit: (questionId: string, selectedOptionId: string, isCorrect: boolean) => void;
  onCTAPress: (intent: ActionIntent) => void;
}

const ComponentView: React.FC<ComponentViewProps> = ({
  component,
  onQuizSubmit,
  onCTAPress,
}) => {
  const fadeAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (component.isVisible) {
      LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
      Animated.spring(fadeAnim, {
        toValue: 1,
        tension: 40,
        friction: 8,
        useNativeDriver: true,
      }).start();
    }
  }, [component.isVisible]);

  const renderComponent = () => {
    switch (component.type) {
      case 'TeacherMessage':
        return <TeacherMessageView message={component as TeacherMessage} />;
      case 'QuizCard':
        return <QuizCardView quiz={component as QuizCard} onSubmit={onQuizSubmit} />;
      case 'CTAButton':
        return <CTAButtonView button={component as CTAButton} onPress={onCTAPress} />;
      case 'Celebration':
        return <CelebrationView celebration={component as Celebration} />;
      default:
        return null;
    }
  };

  return (
    <Animated.View style={[
      styles.componentContainer, 
      { 
        opacity: fadeAnim,
        transform: [{
          translateY: fadeAnim.interpolate({
            inputRange: [0, 1],
            outputRange: [30, 0] // Slide up by 30px
          })
        }]
      }
    ]}>
      {renderComponent()}
    </Animated.View>
  );
};

const TeacherMessageView: React.FC<{ message: TeacherMessage }> = ({ message }) => (
  <View style={styles.teacherMessageWrapper}>
    <View style={styles.avatarPlaceholder}>
      <Text style={styles.avatarEmoji}>👩‍🏫</Text>
    </View>
    <View style={styles.teacherMessageBubble}>
      <Text style={styles.teacherMessageText}>{message.text}</Text>
      {message.emotion && (
        <View style={styles.emotionBadge}>
          <Text style={styles.emotionText}>{message.emotion}</Text>
        </View>
      )}
    </View>
  </View>
);

const QuizCardView: React.FC<{
  quiz: QuizCard;
  onSubmit: (questionId: string, selectedOptionId: string, isCorrect: boolean) => void;
}> = ({ quiz, onSubmit }) => {
  const [selectedOption, setSelectedOption] = useState<string | null>(null);

  const handleOptionSelect = (option: QuizOption) => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setSelectedOption(option.id);
    
    // Slight delay so the user sees the button highlight before progressing
    setTimeout(() => {
      onSubmit(quiz.component_id, option.id, option.is_correct);
    }, 600);
  };

  return (
    <View style={styles.quizCard}>
      <Text style={styles.quizQuestion}>{quiz.question}</Text>
      <View style={styles.quizOptionsContainer}>
        {quiz.options.map((option) => {
          const isSelected = selectedOption === option.id;
          let optionStyle = styles.quizOption;
          let textStyle = styles.quizOptionText;
          
          if (isSelected) {
            optionStyle = option.is_correct 
              ? [styles.quizOption, styles.quizOptionSelectedCorrect] 
              : [styles.quizOption, styles.quizOptionSelectedIncorrect];
            textStyle = styles.quizOptionTextSelected;
          }

          return (
            <TouchableOpacity
              key={option.id}
              activeOpacity={0.7}
              style={optionStyle}
              onPress={() => handleOptionSelect(option)}
              disabled={selectedOption !== null}
            >
              <View style={[styles.radioButton, isSelected && styles.radioButtonSelected]}>
                {isSelected && <View style={styles.radioButtonInner} />}
              </View>
              <Text style={textStyle}>{option.label}</Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
};

const CTAButtonView: React.FC<{
  button: CTAButton;
  onPress: (intent: ActionIntent) => void;
}> = ({ button, onPress }) => (
  <TouchableOpacity
    activeOpacity={0.8}
    style={styles.ctaButtonWrapper}
    onPress={() => onPress(button.action_intent)}
  >
    <View style={styles.ctaButton}>
      <Text style={styles.ctaButtonText}>{button.label}</Text>
    </View>
  </TouchableOpacity>
);

const CelebrationView: React.FC<{ celebration: Celebration }> = ({ celebration }) => {
  const scaleAnim = useRef(new Animated.Value(0.5)).current;

  useEffect(() => {
    Animated.spring(scaleAnim, {
      toValue: 1,
      tension: 50,
      friction: 4,
      useNativeDriver: true,
    }).start();
  }, []);

  return (
    <Animated.View style={[styles.celebration, { transform: [{ scale: scaleAnim }] }]}>
      <View style={styles.celebrationGlow}>
        <Text style={styles.celebrationEmoji}>✨ 🎉 ✨</Text>
        <Text style={styles.celebrationText}>{celebration.message}</Text>
      </View>
    </Animated.View>
  );
};

// MARK: - Utilities

const generateSessionId = (): string => {
  return 'session_' + Math.random().toString(36).substring(2, 15);
};

// MARK: - Styles

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F7F9FC', // Very light, airy gray/blue
  },
  statusBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingTop: Platform.OS === 'ios' ? 56 : 20,
    paddingBottom: 16,
    backgroundColor: 'rgba(255, 255, 255, 0.9)', // Glassmorphism base
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(0,0,0,0.03)',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.03,
    shadowRadius: 12,
    elevation: 3,
    zIndex: 10,
  },
  statusLeft: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  statusRight: {
    backgroundColor: '#F0F2F5',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
  },
  statusIndicator: {
    width: 10,
    height: 10,
    borderRadius: 5,
    marginRight: 10,
    shadowColor: '#34C759',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.5,
    shadowRadius: 4,
  },
  statusText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#6C757D',
    letterSpacing: 0.3,
  },
  titleText: {
    fontSize: 18,
    fontWeight: '700',
    color: '#111827',
    letterSpacing: -0.4,
  },
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    padding: 20,
    paddingBottom: 100, // Breathing room at the bottom
  },
  componentContainer: {
    marginBottom: 24,
  },
  teacherMessageWrapper: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    marginBottom: 8,
  },
  avatarPlaceholder: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#FFFFFF',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 2,
  },
  avatarEmoji: {
    fontSize: 24,
  },
  teacherMessageBubble: {
    flex: 1,
    backgroundColor: '#FFFFFF',
    padding: 18,
    borderRadius: 20,
    borderBottomLeftRadius: 4, // Tail effect
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.04,
    shadowRadius: 16,
    elevation: 3,
    borderWidth: 1,
    borderColor: 'rgba(0,0,0,0.02)',
  },
  teacherMessageText: {
    fontSize: 16,
    fontWeight: '500',
    color: '#374151',
    lineHeight: 24,
    letterSpacing: 0.2,
  },
  emotionBadge: {
    alignSelf: 'flex-start',
    marginTop: 10,
    backgroundColor: '#F3F4F6',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  emotionText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#6B7280',
    textTransform: 'capitalize',
  },
  quizCard: {
    backgroundColor: '#FFFFFF',
    padding: 24,
    borderRadius: 24,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.06,
    shadowRadius: 24,
    elevation: 5,
    borderWidth: 1,
    borderColor: 'rgba(0,0,0,0.02)',
  },
  quizQuestion: {
    fontSize: 19,
    fontWeight: '700',
    color: '#111827',
    marginBottom: 20,
    lineHeight: 28,
    letterSpacing: -0.3,
  },
  quizOptionsContainer: {
    gap: 12, // React Native supports gap
  },
  quizOption: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    backgroundColor: '#F9FAFB',
    borderRadius: 16,
    borderWidth: 1.5,
    borderColor: '#E5E7EB',
  },
  quizOptionSelectedCorrect: {
    backgroundColor: '#F0FDF4',
    borderColor: '#22C55E',
    shadowColor: '#22C55E',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 8,
  },
  quizOptionSelectedIncorrect: {
    backgroundColor: '#FEF2F2',
    borderColor: '#EF4444',
  },
  radioButton: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 2,
    borderColor: '#D1D5DB',
    marginRight: 14,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
  },
  radioButtonSelected: {
    borderColor: '#3B82F6',
  },
  radioButtonInner: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: '#3B82F6',
  },
  quizOptionText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#4B5563',
    flex: 1,
  },
  quizOptionTextSelected: {
    color: '#111827',
  },
  ctaButtonWrapper: {
    shadowColor: '#4F46E5',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.25,
    shadowRadius: 16,
    elevation: 6,
    marginVertical: 8,
  },
  ctaButton: {
    backgroundColor: '#4F46E5', // Premium Indigo
    paddingVertical: 18,
    paddingHorizontal: 24,
    borderRadius: 100, // Fully rounded pill
    alignItems: 'center',
    justifyContent: 'center',
  },
  ctaButtonText: {
    fontSize: 18,
    fontWeight: '700',
    color: '#FFFFFF',
    letterSpacing: 0.5,
  },
  celebration: {
    marginVertical: 16,
  },
  celebrationGlow: {
    backgroundColor: 'rgba(254, 240, 138, 0.4)',
    padding: 32,
    borderRadius: 32,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'rgba(250, 204, 21, 0.5)',
    shadowColor: '#EAB308',
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.2,
    shadowRadius: 24,
    elevation: 8,
  },
  celebrationEmoji: {
    fontSize: 54,
    marginBottom: 12,
    textShadowColor: 'rgba(0,0,0,0.1)',
    textShadowOffset: { width: 0, height: 4 },
    textShadowRadius: 8,
  },
  celebrationText: {
    fontSize: 22,
    fontWeight: '800',
    color: '#B45309',
    textAlign: 'center',
    letterSpacing: 0.5,
  },
  errorContainer: {
    position: 'absolute',
    bottom: 40,
    left: 20,
    right: 20,
    backgroundColor: '#FEF2F2',
    padding: 16,
    borderRadius: 16,
    borderLeftWidth: 4,
    borderLeftColor: '#EF4444',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 4,
  },
  errorText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#991B1B',
  },
});

export default LivingClassroomView;