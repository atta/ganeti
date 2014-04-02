{-| Implementation of a priority waiting structure for locks.

-}

{-

Copyright (C) 2014 Google Inc.

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
02110-1301, USA.

-}

module Ganeti.Locking.Waiting
 ( LockWaiting
 , emptyWaiting
 , updateLocks
 , updateLocksWaiting
 , getAllocation
 ) where

import qualified Data.Map as M
import Data.Maybe (fromMaybe)
import qualified Data.Set as S

import Ganeti.BasicTypes
import qualified Ganeti.Locking.Allocation as L
import Ganeti.Locking.Types (Lock)

{-

This module is parametric in the type of locks, lock owners, and priorities of
the request. While we state only minimal requirements for the types, we will
consistently use the type variable 'a' for the type of locks, the variable 'b'
for the type of the lock owners, and 'c' for the type of priorities throughout
this module. The type 'c' will have to instance Ord, and the smallest value
indicate the most important priority.

-}

{-| Representation of the waiting structure

For any request we cannot fullfill immediately, we have a set of lock
owners it is blocked on. We can pick one of the owners, the smallest say;
then we know that this request cannot possibly be fulfilled until this
owner does something. So we can index the pending requests by such a chosen
owner and only revisit them once the owner acts. For the requests to revisit
we need to do so in order of increasing priority; this order can be maintained
by the Set data structure, where we make use of the fact that tuples are ordered
lexicographically.

Additionally, we keep track of which owners have pending requests, to disallow
them any other lock tasks till their request is fulfilled. To allow canceling
of pending requests, we also keep track on which owner their request is pending
on and what the request was.

-}

data LockWaiting a b c =
  LockWaiting { lwAllocation :: L.LockAllocation a b
              , lwPending :: M.Map b (S.Set (c, b, [L.LockRequest a]))
              , lwPendingOwners :: M.Map b (b, (c, b, [L.LockRequest a]))
              } deriving Show

-- | A state without locks and pending requests.
emptyWaiting :: (Ord a, Ord b, Ord c) => LockWaiting a b c
emptyWaiting =
  LockWaiting { lwAllocation = L.emptyAllocation
              , lwPending = M.empty
              , lwPendingOwners = M.empty
              }

-- | Get the allocation state from the waiting state
getAllocation :: LockWaiting a b c -> L.LockAllocation a b
getAllocation = lwAllocation

-- | Internal function to fulfill one request if possible, and keep track of
-- the owners to be notified. The type is chosen to be suitable as fold
-- operation.
--
-- This function calls the later defined updateLocksWaiting, as they are
-- mutually recursive.
tryFulfillRequest :: (Lock a, Ord b, Ord c)
                  => (LockWaiting a b c, S.Set b)
                  -> (c, b, [L.LockRequest a])
                  -> (LockWaiting a b c, S.Set b)
tryFulfillRequest (waiting, toNotify) (prio, owner, req) =
  let (waiting', (_, newNotify)) = updateLocksWaiting prio owner req waiting
  in (waiting', toNotify `S.union` newNotify)

-- | Internal function to recursively follow the consequences of a change.
revisitRequests :: (Lock a, Ord b, Ord c)
                => S.Set b -- ^ the owners where the requests keyed by them
                           -- already have been revisited
                -> S.Set b -- ^ the owners where requests keyed by them need
                           -- to be revisited
                -> LockWaiting a b c -- ^ state before revisiting
                -> (S.Set b, LockWaiting a b c) -- ^ owners visited and state
                                                -- after revisiting
revisitRequests notify todo state =
  let getRequests (pending, reqs) owner =
        (M.delete owner pending
        , fromMaybe S.empty (M.lookup owner pending) `S.union` reqs)
      (pending', requests) = S.foldl getRequests (lwPending state, S.empty) todo
      revisitedOwners = S.map (\(_, o, _) -> o) requests
      pendingOwners' = S.foldl (flip M.delete) (lwPendingOwners state)
                               revisitedOwners
      state' = state { lwPending = pending', lwPendingOwners = pendingOwners' }
      (state'', notify') = S.foldl tryFulfillRequest (state', notify) requests
      done = notify `S.union` todo
      newTodo = notify' S.\\ done
  in if S.null todo
       then (notify, state)
       else revisitRequests done newTodo state''

-- | Update the locks on an onwer according to the given request, if possible.
-- Additionally (if the request succeeds) fulfill any pending requests that
-- became possible through this request. Return the new state of the waiting
-- structure, the result of the operation, and a list of nodes to be notified
-- that their locks are available now. The result is, as for lock allocation,
-- the set of owners the request is blocked on. Again, the type is chosen to be
-- suitable for use in atomicModifyIORef.
updateLocks :: (Lock a, Ord b, Ord c)
            => b
            -> [L.LockRequest a]
            -> LockWaiting a b c
            -> (LockWaiting a b c, (Result (S.Set b), S.Set b))
updateLocks owner reqs state =
  let (allocation', result) = L.updateLocks owner reqs (lwAllocation state)
      state' = state { lwAllocation = allocation' }
      (notify, state'') = revisitRequests S.empty (S.singleton owner) state'
  in if M.member owner $ lwPendingOwners state
       then ( state
            , (Bad "cannot update locks while having pending requests", S.empty)
            )
       else if result /= Ok S.empty -- skip computation if request could not
                                    -- be handled anyway
              then (state, (result, S.empty))
              else let pendingOwners' = lwPendingOwners state''
                       toNotify = S.filter (not . flip M.member pendingOwners')
                                           notify
                   in (state'', (result, toNotify))

-- | Update locks as soon as possible. If the request cannot be fulfilled
-- immediately add the request to the waiting queue. The first argument is
-- the priority at which the owner is waiting, the remaining are as for
-- updateLocks, and so is the output.
updateLocksWaiting :: (Lock a, Ord b, Ord c)
                   => c
                   -> b
                   -> [L.LockRequest a]
                   -> LockWaiting a b c
                   -> (LockWaiting a b c, (Result (S.Set b), S.Set b))
updateLocksWaiting prio owner reqs state =
  let (state', (result, notify)) = updateLocks owner reqs state
      state'' = case result of
        Bad _ -> state' -- bad requests cannot be queued
        Ok empty | S.null empty -> state'
        Ok blocked -> let blocker = S.findMin blocked
                          owners = M.insert owner (blocker, (prio, owner, reqs))
                                     $ lwPendingOwners state
                          pendingEntry = S.insert (prio, owner, reqs)
                                           . fromMaybe S.empty
                                           . M.lookup blocker
                                           $ lwPending state
                          pending = M.insert blocker pendingEntry
                                      $ lwPending state
                      in state' { lwPendingOwners = owners
                                , lwPending = pending
                                }
  in (state'', (result, notify))
