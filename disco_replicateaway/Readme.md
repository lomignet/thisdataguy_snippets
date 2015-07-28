Before removing a node from Disco, the right way to do it is to blacklist it, replicate away its data, and finally remove it form the cluster. Replicating data away is done by running the garbage collector. Unfortunately, the garbage collector does not migrate everything in one go, so a few runs are needed. To not have to do this manually, the following script will run the garbage collector as often as needed as long as some nodes are blacklisted but not yet safe for removal.


This is the accompanying script for the blog post describing its use at http://thisdataguy.com/2014/02/10/disco-replicate-all-data-away-from-a-blacklisted-node/.
