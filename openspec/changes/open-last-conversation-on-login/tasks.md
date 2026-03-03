## 1. Fix Login Conversation Race Condition

- [x] 1.1 Modify useEffect in App.tsx to add authToken check
  - Add authToken to the dependency array
  - Add check: if !authToken, return early (not logged in)
- [x] 1.2 Update condition logic to prevent premature new conversation creation
  - When justLoggedInRef.current is true but serverConversations is empty, wait for load to complete
  - Only create new conversation when explicitly no history exists after load

## 2. Testing

- [ ] 2.1 Test login with existing conversation history
  - Login with user who has previous conversations
  - Verify most recent conversation is loaded (not new)
- [ ] 2.2 Test login with no conversation history
  - Login with fresh user account
  - Verify new conversation is created
- [ ] 2.3 Test race condition fix
  - Monitor console logs during login
  - Verify no new conversation created before serverConversations loads
- [ ] 2.4 Test page refresh behavior
  - Login and verify correct conversation loads
  - Refresh page and verify conversation persists

## 3. Verification

- [x] 3.1 Run lint check on modified files
  - Note: Pre-existing lint errors in codebase, not related to this change
- [ ] 3.2 Verify no console errors during login flow
